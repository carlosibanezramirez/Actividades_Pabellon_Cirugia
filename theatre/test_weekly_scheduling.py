from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Intervention, Reservation
from .scheduling import day_slots, reserve_hours
from .services import create_intervention
from .tests import fixtures
from .weekly_scheduling import continuous_day, reserve_continuous, week_start


class WeeklySchedulingTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()
        self.room = self.intervention.room
        self.day = timezone.localdate() + timedelta(days=4)
        self.client.force_login(self.user)

    def reserve(self, desired_time=time(9, 30), duration_minutes=90, **overrides):
        args = dict(user=self.user, room=self.room, day=self.day, desired_time=desired_time,
                    duration_minutes=duration_minutes, doctor=self.intervention.doctor,
                    procedure=self.intervention.procedure, patient_name='Paciente ficticio semanal')
        args.update(overrides)
        return reserve_continuous(**args)

    def test_0930_for_90_minutes_occupies_0915_to_1100(self):
        booking = self.reserve()
        local = timezone.localtime
        self.assertEqual(local(booking.starts_at).time(), time(9, 15))
        self.assertEqual(local(booking.planned_start_at).time(), time(9, 30))
        self.assertEqual(local(booking.ends_at).time(), time(11))
        self.assertEqual(booking.planned_duration_minutes, 90)
        self.assertEqual(booking.created_by, self.user)
        self.assertEqual(booking.patient_name, 'Paciente ficticio semanal')

    def test_no_hour_rounding_and_short_interventions_are_allowed(self):
        booking = self.reserve(time(9), 20)
        self.assertEqual(booking.ends_at - booking.starts_at, timedelta(minutes=35))
        day = continuous_day(self.room, self.day)
        busy = [segment for segment in day['segments'] if segment['busy']]
        self.assertEqual(len(busy), 1)
        self.assertEqual(busy[0]['start'], booking.starts_at)
        self.assertEqual(busy[0]['end'], booking.ends_at)
        self.assertEqual(day['free_minutes'], 1440 - 35)
        self.assertEqual(sum((s['end'] - s['start']).total_seconds() for s in day['segments']), 24 * 3600)

    def test_initial_day_is_a_single_green_continuous_interval(self):
        day = continuous_day(self.room, self.day)
        self.assertEqual(len(day['segments']), 1)
        self.assertFalse(day['segments'][0]['busy'])
        self.assertEqual(day['segments'][0]['height'], '100.000000')

    def test_overlap_in_preparation_alone_prevents_booking(self):
        slots = day_slots(self.day)
        index = next(s['index'] for s in slots if timezone.localtime(s['start']).time() == time(8))
        reserve_hours(user=self.user, day=self.day, selections=[f'{self.room.pk}:{index}'],
                      doctor=self.intervention.doctor, procedure=self.intervention.procedure,
                      patient_name='Paciente ficticio anterior')
        with self.assertRaises(ValidationError):
            self.reserve(time(9), 20)
        self.reserve(time(9, 30), 20)

    def test_adjacent_intervals_are_allowed_but_intersections_are_rejected(self):
        self.reserve(time(9), 45)  # 08:45–09:45
        with self.assertRaises(ValidationError):
            self.reserve(time(9, 30), 20)
        booking = self.reserve(time(10), 45)  # 09:45–10:45
        self.assertEqual(timezone.localtime(booking.starts_at).time(), time(9, 45))

    def test_preparation_checks_previous_day_and_is_shown_on_both_days(self):
        booking = self.reserve(time(0), 30)
        self.assertEqual(timezone.localtime(booking.starts_at).date(), self.day - timedelta(days=1))
        before = continuous_day(self.room, self.day - timedelta(days=1))
        selected = continuous_day(self.room, self.day)
        self.assertEqual(sum(int((s['end'] - s['start']).total_seconds() // 60) for s in before['segments'] if s['busy']), 15)
        self.assertEqual(sum(int((s['end'] - s['start']).total_seconds() // 60) for s in selected['segments'] if s['busy']), 30)
        with self.assertRaises(ValidationError):
            self.reserve(time(23, 30), 30, day=self.day - timedelta(days=1))

    def test_intervention_crossing_midnight_marks_next_day_and_blocks_hourly_agenda(self):
        self.reserve(time(23, 30), 120)
        next_day = self.day + timedelta(days=1)
        following = continuous_day(self.room, next_day)
        busy_minutes = sum((s['end'] - s['start']).total_seconds() // 60 for s in following['segments'] if s['busy'])
        self.assertEqual(busy_minutes, 90)
        with self.assertRaises(ValidationError):
            reserve_hours(user=self.user, day=next_day, selections=[f'{self.room.pk}:0'],
                          doctor=self.intervention.doctor, procedure=self.intervention.procedure,
                          patient_name='Paciente ficticio horario')

    def test_only_half_hour_starts_positive_minutes_and_future_preparation_are_accepted(self):
        for clock in [time(9, 15), time(9, 30, 1)]:
            with self.subTest(clock=clock), self.assertRaises(ValidationError):
                self.reserve(clock, 20)
        for value in [0, -1, 3.5, True, 1441]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.reserve(duration_minutes=value)
        local_start = timezone.make_aware(datetime.combine(self.day, time(9)))
        with patch('theatre.weekly_scheduling.timezone.now', return_value=local_start - timedelta(minutes=10)):
            with self.assertRaises(ValidationError):
                self.reserve(time(9), 20)

    def test_dst_nonexistent_or_ambiguous_start_is_rejected(self):
        future_now = timezone.make_aware(datetime(2026, 1, 1)).astimezone(datetime_timezone.utc)
        with patch('theatre.weekly_scheduling.timezone.now', return_value=future_now):
            with self.assertRaises(ValidationError):
                self.reserve(time(0), 30, day=datetime(2026, 9, 6).date())
            with self.assertRaises(ValidationError):
                self.reserve(time(23, 30), 30, day=datetime(2026, 4, 4).date())

    def test_week_renders_seven_days_monday_through_sunday_and_click_opens_one_day(self):
        response = self.client.get(reverse('weekly_agenda'), {'room': self.room.pk, 'fecha': self.day.isoformat()})
        self.assertEqual(response.status_code, 200)
        days = response.context['days']
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]['date'], week_start(self.day))
        self.assertEqual(days[-1]['date'].weekday(), 6)
        url = reverse('weekly_day', args=[self.room.pk, self.day.isoformat()])
        self.assertContains(response, url)
        daily = self.client.get(url)
        self.assertEqual(daily.context['day']['date'], self.day)
        self.assertNotContains(daily, 'week-grid')
        self.assertContains(daily, 'Nombre del paciente')

    def test_daily_post_saves_patient_then_returns_to_day_with_red_interval(self):
        url = reverse('weekly_day', args=[self.room.pk, self.day.isoformat()])
        response = self.client.post(url, {
            'doctor': self.intervention.doctor_id, 'procedure': self.intervention.procedure_id,
            'patient_name': 'Paciente ficticio del formulario', 'desired_time': '09:30',
            'duration_minutes': '90',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        booking = Reservation.objects.get()
        self.assertEqual(booking.patient_name, 'Paciente ficticio del formulario')
        self.assertTrue(any(s['busy'] for s in response.context['day']['segments']))
        self.assertContains(response, '09:15')
        self.assertContains(response, '11:00')
        self.assertContains(response, 'Reserva #')

    def test_invalid_patient_or_time_does_not_save_and_conflicts_are_reported(self):
        url = reverse('weekly_day', args=[self.room.pk, self.day.isoformat()])
        data = {'doctor': self.intervention.doctor_id, 'procedure': self.intervention.procedure_id,
                'patient_name': '', 'desired_time': '09:15', 'duration_minutes': '20'}
        response = self.client.post(url, data)
        self.assertIn('patient_name', response.context['form'].errors)
        self.assertIn('desired_time', response.context['form'].errors)
        self.assertEqual(Reservation.objects.count(), 0)
        self.reserve()
        response = self.client.post(url, {**data, 'patient_name': 'Paciente ficticio', 'desired_time': '09:30'})
        self.assertContains(response, 'No hay espacio para el intervalo completo')
        self.assertEqual(Reservation.objects.count(), 1)

    def test_linked_short_reservation_can_start_without_imposing_old_hour_minimum(self):
        booking = self.reserve(time(9), 20)  # 08:45–09:20
        self.reserve(time(10), 20)  # 09:45–10:20
        Intervention.objects.filter(pk=self.intervention.pk).update(completed_at=timezone.now())
        with patch('theatre.services.timezone.now', return_value=booking.starts_at + timedelta(minutes=5)):
            item = create_intervention(user=self.user, room=self.room,
                                       doctor=self.intervention.doctor, procedure=self.intervention.procedure,
                                       anesthetist=self.intervention.anesthetist, reservation=booking)
        self.assertEqual(item.reservation_id, booking.pk)

    def test_database_checks_the_fifteen_minutes_and_legacy_minimum(self):
        planned = timezone.make_aware(datetime.combine(self.day, time(9)))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.create(room=self.room, doctor=self.intervention.doctor,
                                       procedure=self.intervention.procedure, patient_name='Paciente ficticio',
                                       starts_at=planned - timedelta(minutes=10), planned_start_at=planned,
                                       ends_at=planned + timedelta(minutes=20), created_by=self.user)

    def test_authentication_permissions_and_disabled_room(self):
        url = reverse('weekly_day', args=[self.room.pk, self.day.isoformat()])
        self.room.active = False
        self.room.save()
        self.assertFalse(self.client.get(url).context['can_book'])
        with self.assertRaises(ValidationError):
            self.reserve()
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        actor = get_user_model().objects.create_user(username='sin-permiso-semana')
        self.client.force_login(actor)
        self.assertEqual(self.client.get(reverse('weekly_agenda')).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo de filas en PostgreSQL')
class WeeklyConcurrencyTests(TransactionTestCase):
    def test_continuous_and_hourly_reservations_cannot_overlap_under_concurrency(self):
        user, _, item = fixtures()
        day = timezone.localdate() + timedelta(days=4)
        barrier = Barrier(2)

        def worker(mode):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                intervention = Intervention.objects.select_related('room', 'doctor', 'procedure').get(pk=item.pk)
                barrier.wait(timeout=10)
                if mode == 'continuous':
                    reserve_continuous(user=actor, room=intervention.room, day=day, desired_time=time(9),
                                       duration_minutes=20, doctor=intervention.doctor, procedure=intervention.procedure,
                                       patient_name='Paciente ficticio continuo')
                else:
                    slot = next(slot for slot in day_slots(day) if timezone.localtime(slot['start']).time() == time(8))
                    reserve_hours(user=actor, day=day, selections=[f'{item.room_id}:{slot["index"]}'],
                                  doctor=intervention.doctor, procedure=intervention.procedure,
                                  patient_name='Paciente ficticio horario')
                return 'ok'
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ['continuous', 'hourly']))
        self.assertCountEqual(results, ['ok', 'rejected'])
        self.assertEqual(Reservation.objects.count(), 1)
