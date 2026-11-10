from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Doctor, Event, Intervention, Reservation, Room
from .scheduling import HOUR, availability, day_slots, reserve_hours
from .services import create_intervention
from .tests import fixtures


class SchedulingTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()
        self.day = timezone.localdate() + timedelta(days=2)
        self.room = self.intervention.room
        self.client.force_login(self.user)

    def reserve(self, *indexes, room=None, **overrides):
        args = dict(user=self.user, day=self.day,
                    selections=[f'{(room or self.room).pk}:{index}' for index in indexes],
                    doctor=self.intervention.doctor, procedure=self.intervention.procedure,
                    patient_name='Paciente ficticio de prueba', patient_rut='12345678-5')
        args.update(overrides)
        return reserve_hours(**args)

    def test_booking_stores_hours_patient_doctor_procedure_and_actor(self):
        booking = self.reserve(9, 10, 11)
        self.assertEqual(booking.ends_at - booking.starts_at, 3 * HOUR)
        self.assertEqual(booking.starts_at, day_slots(self.day)[9]['start'])
        self.assertEqual(booking.patient_name, 'Paciente ficticio de prueba')
        self.assertEqual(booking.doctor, self.intervention.doctor)
        self.assertEqual(booking.procedure, self.intervention.procedure)
        self.assertEqual(booking.created_by, self.user)
        cells = availability(self.day)['rows'][0]['slots']
        self.assertFalse(cells[9]['selectable'])
        self.assertEqual(cells[9]['label'], 'Reservado')
        self.assertEqual(cells[9]['state'], 'no_disponible')
        self.assertTrue(cells[12]['selectable'])

    def test_disjoint_mixed_duplicate_missing_and_invalid_hours_rejected(self):
        another = Room.objects.create(name='Otro pabellón para reservar')
        for selections in [[], [f'{self.room.pk}:9', f'{self.room.pk}:11'],
                           [f'{self.room.pk}:9', f'{another.pk}:10'],
                           [f'{self.room.pk}:9'] * 2, ['incorrecto'],
                           [f'{self.room.pk}:-1'], [f'{self.room.pk}:99']]:
            with self.subTest(selections=selections), self.assertRaises(ValidationError):
                self.reserve(selections=selections)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_overlapping_bookings_rejected_but_adjacent_hours_and_other_rooms_allowed(self):
        self.reserve(9, 10)
        with self.assertRaises(ValidationError):
            self.reserve(10, 11)
        self.reserve(8)
        self.reserve(11)
        other = Room.objects.create(name='Pabellón independiente')
        self.reserve(9, room=other)
        self.assertEqual(Reservation.objects.count(), 4)

    def test_inactive_room_doctor_procedure_and_missing_patient_rejected(self):
        with self.assertRaises(ValidationError):
            self.reserve(9, patient_name='  ', patient_rut='12345678-5')
        self.room.active = False
        self.room.save()
        with self.assertRaises(ValidationError):
            self.reserve(9)
        self.room.active = True
        self.room.save()
        self.intervention.doctor.active = False
        self.intervention.doctor.save()
        with self.assertRaises(ValidationError):
            self.reserve(9)
        self.intervention.doctor.active = True
        self.intervention.doctor.save()
        self.intervention.procedure.active = False
        self.intervention.procedure.save()
        with self.assertRaises(ValidationError):
            self.reserve(9)

    def test_started_or_past_hours_cannot_be_reserved(self):
        slot = day_slots(self.day)[9]
        with patch('theatre.scheduling.timezone.now', return_value=slot['start'] + timedelta(seconds=1)):
            with self.assertRaises(ValidationError):
                self.reserve(9)

    def test_database_rejects_a_reservation_shorter_than_one_hour(self):
        start = day_slots(self.day)[9]['start']
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(room=self.room, doctor=self.intervention.doctor,
                                       procedure=self.intervention.procedure, patient_name='Paciente ficticio', patient_rut='12345678-5',
                                       starts_at=start, ends_at=start + timedelta(minutes=30), created_by=self.user)

    def test_real_short_use_blocks_at_least_one_hour_including_preparation(self):
        day = timezone.localdate() - timedelta(days=1)
        start = day_slots(day)[9]['start']
        Intervention.objects.filter(pk=self.intervention.pk).update(created_at=start, completed_at=start + timedelta(minutes=10))
        for stage, minute in [(1, 0), (2, 5), (9, 10)]:
            Event.objects.create(intervention=self.intervention, stage=stage, occurred_at=start + timedelta(minutes=minute),
                                 original_at=start + timedelta(minutes=minute), recorded_by=self.user)
        cells = availability(day)['rows'][0]['slots']
        self.assertEqual(cells[9]['state'], 'procedimiento')
        self.assertEqual(cells[10]['state'], 'libre')

    def test_preparation_and_open_procedure_block_remaining_current_day(self):
        day = timezone.localdate()
        start = day_slots(day)[9]['start']
        Intervention.objects.filter(pk=self.intervention.pk).update(created_at=start)
        Event.objects.create(intervention=self.intervention, stage=1, occurred_at=start, original_at=start, recorded_by=self.user)
        now = start + timedelta(minutes=10)
        cells = availability(day, now)['rows'][0]['slots']
        self.assertEqual(cells[10]['state'], 'preparacion')
        Event.objects.create(intervention=self.intervention, stage=2, occurred_at=now, original_at=now, recorded_by=self.user)
        cells = availability(day, now)['rows'][0]['slots']
        self.assertEqual(cells[-1]['state'], 'procedimiento')
        self.assertFalse(cells[-1]['selectable'])

    def test_dst_days_use_real_consecutive_one_hour_intervals(self):
        spring = day_slots(date(2026, 9, 6))
        autumn = day_slots(date(2026, 4, 4))
        self.assertEqual(len(spring), 23)
        self.assertEqual(len(autumn), 25)
        for slots in (spring, autumn):
            self.assertTrue(all(slot['end'] - slot['start'] == HOUR for slot in slots))
            self.assertTrue(all(slots[i]['end'] == slots[i + 1]['start'] for i in range(len(slots) - 1)))

    def test_last_hour_can_end_next_day_and_short_use_blocks_across_midnight(self):
        last = day_slots(self.day)[-1]
        booking = self.reserve(last['index'])
        self.assertEqual(booking.ends_at - booking.starts_at, HOUR)
        self.assertEqual(timezone.localtime(booking.ends_at).date(), self.day + timedelta(days=1))
        old_day = timezone.localdate() - timedelta(days=2)
        start = day_slots(old_day)[-1]['start'] + timedelta(minutes=45)
        end = start + timedelta(minutes=10)
        Intervention.objects.filter(pk=self.intervention.pk).update(created_at=start, completed_at=end)
        for stage, at in [(1, start), (2, start + timedelta(minutes=5)), (9, end)]:
            Event.objects.create(intervention=self.intervention, stage=stage, occurred_at=at,
                                 original_at=at, recorded_by=self.user)
        cells = availability(old_day + timedelta(days=1))['rows'][0]['slots']
        self.assertEqual(cells[0]['state'], 'procedimiento')
        self.assertEqual(cells[1]['state'], 'fuera_horario')

    def test_open_intervention_prevents_booking_later_today(self):
        day = timezone.localdate()
        now = day_slots(day)[8]['start']
        start = now - timedelta(minutes=10)
        Intervention.objects.filter(pk=self.intervention.pk).update(created_at=start)
        Event.objects.create(intervention=self.intervention, stage=1, occurred_at=start,
                             original_at=start, recorded_by=self.user)
        with patch('theatre.scheduling.timezone.now', return_value=now):
            with self.assertRaises(ValidationError):
                self.reserve(10, day=day)

    def test_agenda_post_and_reservation_detail(self):
        response = self.client.get(reverse('agenda'), {'fecha': self.day.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, day_slots(self.day)[9]['label'])
        data = {'fecha': self.day.isoformat(), 'slots': [f'{self.room.pk}:9', f'{self.room.pk}:10'],
                'doctor': self.intervention.doctor_id, 'procedure': self.intervention.procedure_id,
                'patient_name': 'Paciente ficticio formulario', 'patient_rut': '12345678-5'}
        response = self.client.post(reverse('agenda'), data)
        self.assertEqual(response.status_code, 302)
        booking = Reservation.objects.get()
        self.assertRedirects(response, reverse('reservation_detail', args=[booking.pk]))
        detail = self.client.get(response.url)
        self.assertContains(detail, 'Paciente ficticio formulario')
        self.assertContains(detail, 'Médico solicitante')
        self.assertContains(detail, 'Tipo de cirugía')

    def test_invalid_date_missing_patient_and_invalid_selection_do_not_save(self):
        response = self.client.get(reverse('agenda'), {'fecha': 'invalida'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['schedule'])
        response = self.client.post(reverse('agenda'), {
            'fecha': self.day.isoformat(), 'slots': [f'{self.room.pk}:9'],
            'doctor': self.intervention.doctor_id, 'procedure': self.intervention.procedure_id,
        })
        self.assertIn('patient_name', response.context['form'].errors)
        self.assertFalse(Reservation.objects.exists())

    def test_start_from_reservation_checks_window_and_matching_data(self):
        booking = self.reserve(9, 10)
        Intervention.objects.filter(pk=self.intervention.pk).update(completed_at=timezone.now())
        args = dict(user=self.user, room=self.room, doctor=self.intervention.doctor,
                    procedure=self.intervention.procedure, anesthetist=self.intervention.anesthetist)
        with self.assertRaises(ValidationError):
            create_intervention(**args, reservation=booking)
        with patch('theatre.services.timezone.now', return_value=booking.starts_at + timedelta(minutes=5)):
            with self.assertRaises(ValidationError):
                create_intervention(**args)
            with self.assertRaises(ValidationError):
                create_intervention(**{**args, 'doctor': self.intervention.anesthetist}, reservation=booking)
            intervention = create_intervention(**args, reservation=booking)
            self.assertEqual(intervention.reservation, booking)
            Intervention.objects.filter(pk=intervention.pk).update(completed_at=timezone.now())
            with self.assertRaises(ValidationError):
                create_intervention(**args, reservation=booking)
        response = self.client.get(reverse('create'), {'reserva': booking.pk})
        self.assertContains(response, booking.patient_name)
        self.assertEqual(response.context['form'].initial['reservation'], booking.pk)
        self.assertEqual(self.client.get(reverse('create'), {'reserva': 'abc'}).status_code, 404)

    def test_permissions_and_csrf_protect_patient_records_and_booking(self):
        booking = self.reserve(9)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('reservation_detail', args=[booking.pk])).status_code, 302)
        user = get_user_model().objects.create_user(username='sin-permiso-agenda')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('agenda')).status_code, 403)
        self.assertEqual(self.client.get(reverse('reservation_detail', args=[booking.pk])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.reserve(10, user=user)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse('agenda'), {}).status_code, 403)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo de filas en PostgreSQL')
class ReservationConcurrencyTests(TransactionTestCase):
    def test_booking_and_unplanned_intervention_cannot_claim_same_room_at_once(self):
        user, _, previous = fixtures()
        Intervention.objects.filter(pk=previous.pk).update(completed_at=timezone.now())
        day = timezone.localdate() + timedelta(days=2)
        now = day_slots(day)[9]['start']
        barrier = Barrier(2)

        def worker(action):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                item = Intervention.objects.select_related('room', 'doctor', 'procedure', 'anesthetist').get(pk=previous.pk)
                barrier.wait(timeout=10)
                if action == 'reserve':
                    reserve_hours(user=actor, day=day, selections=[f'{item.room_id}:9'],
                                  doctor=item.doctor, procedure=item.procedure,
                                  patient_name='Paciente ficticio simultáneo', patient_rut='12345678-5')
                else:
                    create_intervention(user=actor, room=item.room, doctor=item.doctor,
                                        procedure=item.procedure, anesthetist=item.anesthetist)
                return 'ok'
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()

        with patch('theatre.scheduling.timezone.now', return_value=now):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(worker, ['reserve', 'intervention']))
        self.assertCountEqual(results, ['ok', 'rejected'])

    def test_two_overlapping_requests_save_only_one_reservation(self):
        user, _, intervention = fixtures()
        barrier = Barrier(2)
        day = timezone.localdate() + timedelta(days=2)

        def worker(indexes):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                reserve_hours(user=actor, day=day,
                              selections=[f'{intervention.room_id}:{index}' for index in indexes],
                              doctor=intervention.doctor, procedure=intervention.procedure,
                              patient_name='Paciente ficticio concurrente', patient_rut='12345678-5')
                return 'ok'
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, [[9, 10], [10, 11]]))
        self.assertCountEqual(results, ['ok', 'rejected'])
        self.assertEqual(Reservation.objects.count(), 1)
