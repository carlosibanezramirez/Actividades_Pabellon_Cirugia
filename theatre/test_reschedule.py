from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Reservation, Room
from .tests import fixtures
from .weekly_scheduling import reserve_continuous, reschedule_reservation, reservation_revision


class RescheduleTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=7)
        self.room = self.item.room
        self.other = Room.objects.create(name='Pabellón destino')
        self.booking = self.reserve()
        self.client.force_login(self.user)

    def reserve(self, **overrides):
        args = dict(user=self.user, room=self.room, day=self.day, desired_time=time(9, 30), duration_minutes=90,
                    doctor=self.item.doctor, procedure=self.item.procedure, patient_name='Paciente ficticio edición',
                    patient_rut='12345678-5')
        args.update(overrides)
        return reserve_continuous(**args)

    def move(self, **overrides):
        args = dict(user=self.user, reservation_id=self.booking.pk, room=self.room,
                    day=self.day + timedelta(days=1), desired_time=time(11),
                    expected_revision=reservation_revision(self.booking))
        args.update(overrides)
        return reschedule_reservation(**args)

    def test_move_preserves_identity_duration_preparation_and_patient(self):
        old = self.booking
        updated = self.move(room=self.other)
        self.assertEqual(updated.pk, old.pk)
        self.assertEqual(updated.room, self.other)
        self.assertEqual(updated.planned_duration_minutes, 90)
        self.assertEqual(updated.preparation_minutes, 15)
        self.assertEqual(updated.patient_rut, old.patient_rut)
        self.assertEqual(updated.patient_name, old.patient_name)
        self.assertEqual(updated.doctor, old.doctor)
        self.assertEqual(updated.procedure, old.procedure)
        self.assertEqual(updated.created_by, old.created_by)
        self.assertEqual(updated.created_at, old.created_at)
        self.assertEqual(timezone.localtime(updated.starts_at).time(), time(10, 45))
        self.assertEqual(timezone.localtime(updated.ends_at).time(), time(12, 30))
        self.assertEqual(Reservation.objects.count(), 1)
        self.reserve()  # El horario original queda liberado.

    def test_same_slot_does_not_conflict_with_itself(self):
        updated = self.move(day=self.day, desired_time=time(9, 30))
        self.assertEqual(updated.starts_at, self.booking.starts_at)

    def test_moving_later_excludes_its_old_end_from_continuity_rule(self):
        updated = self.move(day=self.day, desired_time=time(15))
        self.assertEqual(timezone.localtime(updated.planned_start_at).time(), time(15))

    def test_overlap_in_destination_preparation_rolls_back(self):
        self.reserve(room=self.other, desired_time=time(10), duration_minutes=60)
        with self.assertRaises(ValidationError):
            self.move(room=self.other, day=self.day, desired_time=time(11))
        original = Reservation.objects.get(pk=self.booking.pk)
        self.assertEqual(original.room_id, self.room.pk)
        self.assertEqual(original.starts_at, self.booking.starts_at)

    def test_room_hours_half_hours_inactive_and_continuity_are_enforced(self):
        self.other.closing_time = time(18)
        self.other.save()
        for clock in [time(6, 30), time(18, 30), time(10, 15)]:
            with self.subTest(clock=clock), self.assertRaises(ValidationError):
                self.move(room=self.other, desired_time=clock)
        self.reserve(room=self.other, day=self.day + timedelta(days=1), desired_time=time(9), duration_minutes=60)
        with self.assertRaises(ValidationError):
            self.move(room=self.other, desired_time=time(11))
        self.other.active = False
        self.other.save()
        with self.assertRaises(ValidationError):
            self.move(room=self.other)

    def test_overnight_move_and_next_day_overlap(self):
        moved = self.move(desired_time=time(23))
        self.assertEqual(timezone.localtime(moved.ends_at).date(), self.day + timedelta(days=2))
        self.assertEqual(timezone.localtime(moved.ends_at).time(), time(0, 30))
        self.booking.refresh_from_db()
        self.other.opening_time = time(0)
        self.other.save()
        self.reserve(room=self.other, day=self.day + timedelta(days=2), desired_time=time(0), duration_minutes=90)
        with self.assertRaises(ValidationError):
            self.move(room=self.other, desired_time=time(23))

    def test_started_intervention_or_past_reservation_cannot_move(self):
        self.item.reservation = self.booking
        self.item.save()
        with self.assertRaises(ValidationError):
            self.move()
        self.item.reservation = None
        self.item.save()
        Reservation.objects.filter(pk=self.booking.pk).update(
            starts_at=timezone.now() - timedelta(hours=2), planned_start_at=timezone.now() - timedelta(minutes=105),
            ends_at=timezone.now() - timedelta(minutes=15))
        self.booking.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.move()

    def test_stale_edits_do_not_overwrite_changes(self):
        self.move()
        with self.assertRaises(ValidationError):
            self.move(room=self.other)

    def test_legacy_reservation_keeps_duration_and_blank_rut(self):
        Reservation.objects.filter(pk=self.booking.pk).update(planned_start_at=None, patient_rut='')
        self.booking.refresh_from_db()
        duration = self.booking.ends_at - self.booking.starts_at
        moved = self.move()
        self.assertIsNone(moved.planned_start_at)
        self.assertEqual(moved.ends_at - moved.starts_at, duration)
        self.assertEqual(moved.patient_rut, '')

    def test_endpoint_prefills_updates_errors_and_signed_revision(self):
        url = reverse('reservation_edit', args=[self.booking.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial['room'], self.room.pk)
        self.assertEqual(form.initial['desired_time'], '09:30')
        data = dict(room=self.other.pk, fecha=(self.day + timedelta(days=1)).isoformat(),
                    desired_time='11:00', revision=form.initial['revision'])
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'room={self.other.pk}', response.json()['redirect_url'])
        self.assertEqual(self.client.post(url, data).status_code, 422)
        data['revision'] = 'alterada'
        self.assertEqual(self.client.post(url, data).status_code, 422)
        self.assertEqual(self.client.post(url, {**data, 'desired_time': '11:15'}).status_code, 422)
        weekly = self.client.get(reverse('weekly_agenda'), {'room': self.other.pk, 'fecha': data['fecha']})
        self.assertContains(weekly, f'data-edit-url="{url}"')
        self.assertContains(weekly, 'reservation-edit-dialog')

    def test_permissions_required(self):
        self.client.logout()
        url = reverse('reservation_edit', args=[self.booking.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        outsider = get_user_model().objects.create_user(username='sin-permiso-edicion')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.move(user=outsider)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo real de PostgreSQL')
class RescheduleConcurrencyTests(TransactionTestCase):
    def test_concurrent_edits_into_same_room_allow_one_only(self):
        user, _, item = fixtures()
        destination = Room.objects.create(name='Destino compartido')
        source = Room.objects.create(name='Otro origen')
        day = timezone.localdate() + timedelta(days=7)
        bookings = [reserve_continuous(user=user, room=room, day=day, desired_time=time(9),
                                      duration_minutes=90, doctor=item.doctor, procedure=item.procedure,
                                      patient_name='Paciente ficticio concurrencia', patient_rut='12345678-5')
                    for room in [item.room, source]]
        barrier = Barrier(2)

        def move(booking):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                target = Room.objects.get(pk=destination.pk)
                barrier.wait(timeout=10)
                try:
                    reschedule_reservation(user=actor, reservation_id=booking.pk, room=target, day=day,
                                           desired_time=time(12), expected_revision=reservation_revision(booking))
                    return 'saved'
                except ValidationError:
                    return 'conflict'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(move, bookings))
        self.assertCountEqual(results, ['saved', 'conflict'])
        self.assertEqual(Reservation.objects.filter(room=destination).count(), 1)
