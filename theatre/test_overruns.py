from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from unittest import skipUnless
from io import StringIO

from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import AutomaticRelocation, Event, Intervention, OperatingSettings, Reservation, Room
from .overruns import process_overruns, relocate_next_reservation
from .tests import fixtures


class OverrunRelocationTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=7)
        self.source = self.item.room
        self.target = Room.objects.create(name='Pabellón alternativo mayor')
        Room.objects.create(name='Urgencias', room_type=Room.Type.EMERGENCY)
        Room.objects.create(name='Menores', room_type=Room.Type.MINOR)
        Room.objects.create(name='Inactivo', active=False)
        self.booking = self.book(self.source, time(9), time(11))
        self.following = self.book(self.source, time(11), time(13))
        self.item.reservation = self.booking
        self.item.save()
        at = self.at(time(10))
        Event.objects.create(intervention=self.item, stage=6, occurred_at=at, original_at=at, recorded_by=self.user)
        self.now = self.at(time(11, 10))

    def at(self, clock):
        return timezone.make_aware(datetime.combine(self.day, clock))

    def book(self, room, start, end):
        instant = self.at(start)
        return Reservation.objects.create(room=room, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio traslado', patient_rut='12345678-5', diagnosis='Diagnóstico ficticio',
            starts_at=instant, planned_start_at=instant + timedelta(minutes=15), ends_at=self.at(end), created_by=self.user)

    def test_exact_threshold_preserves_every_reservation_field_except_room(self):
        before = (self.following.starts_at, self.following.planned_start_at, self.following.ends_at,
                  self.following.patient_name, self.following.patient_rut, self.following.diagnosis)
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now - timedelta(microseconds=1)))
        move = relocate_next_reservation(self.item.pk, self.now)
        self.assertEqual(move.to_room, self.target)
        self.following.refresh_from_db()
        self.assertEqual(self.following.room, self.target)
        self.assertEqual(before, (self.following.starts_at, self.following.planned_start_at, self.following.ends_at,
                                 self.following.patient_name, self.following.patient_rut, self.following.diagnosis))
        self.assertEqual(self.following.created_by, self.user)
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now + timedelta(hours=1)))
        self.assertEqual(AutomaticRelocation.objects.count(), 1)

    def test_configurable_grace_and_worker_command(self):
        policy = OperatingSettings.current()
        self.assertEqual(policy.allowed_overrun_minutes, 10)
        policy.allowed_overrun_minutes = 20
        policy.save()
        self.assertEqual(process_overruns(self.now), 0)
        self.assertEqual(process_overruns(self.now + timedelta(minutes=10)), 1)
        output = StringIO()
        call_command('monitor_overruns', once=True, stdout=output)
        self.assertIn('Reasignaciones realizadas', output.getvalue())

    def test_unavailable_or_wrong_category_rooms_are_never_assigned_and_retry_succeeds(self):
        self.book(self.target, time(10, 30), time(12))
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now))
        self.assertEqual(AutomaticRelocation.objects.count(), 0)
        free = Room.objects.create(name='Otra alternativa mayor')
        self.assertEqual(relocate_next_reservation(self.item.pk, self.now).to_room, free)

    def test_pending_preoperative_moves_with_reservation(self):
        pending = Intervention.objects.create(room=self.source, procedure=self.item.procedure,
            doctor=self.item.doctor, anesthetist=self.item.anesthetist, created_by=self.user,
            reservation=self.following, room_engaged=False)
        relocate_next_reservation(self.item.pk, self.now)
        pending.refresh_from_db()
        self.assertEqual(pending.room, self.target)
        self.assertFalse(pending.room_engaged)

    def test_already_started_schedule_still_moves_at_identical_time(self):
        self.following.planned_start_at = self.at(time(11, 5))
        self.following.save()
        self.assertIsNotNone(relocate_next_reservation(self.item.pk, self.now))
        self.following.refresh_from_db()
        self.assertEqual(self.following.planned_start_at, self.at(time(11, 5)))

    def test_finished_cancelled_and_emergency_sources_do_not_trigger(self):
        self.item.completed_at = self.now
        self.item.save()
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now))
        self.item.completed_at = None
        self.item.save()
        self.booking.cancelled_at = self.now
        self.booking.save()
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now))
        self.booking.cancelled_at = None
        self.booking.save()
        self.source.room_type = Room.Type.EMERGENCY
        self.source.save()
        self.assertIsNone(relocate_next_reservation(self.item.pk, self.now))

    def test_only_first_reservation_is_moved_once(self):
        later = self.book(self.source, time(13), time(15))
        self.assertEqual(process_overruns(self.now), 1)
        self.assertEqual(process_overruns(self.now), 0)
        later.refresh_from_db()
        self.assertEqual(later.room, self.source)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo de PostgreSQL')
class RelocationConcurrencyTests(TransactionTestCase):
    def test_two_monitors_move_following_reservation_only_once(self):
        user, _, item = fixtures()
        day = timezone.localdate() + timedelta(days=7)
        instant = timezone.make_aware(datetime.combine(day, time(11)))
        target = Room.objects.create(name='Destino libre')
        def booking(start, end):
            return Reservation.objects.create(room=item.room, doctor=item.doctor, procedure=item.procedure,
                patient_name='Paciente ficticio simultáneo', starts_at=start,
                planned_start_at=start + timedelta(minutes=15), ends_at=end, created_by=user)
        source = booking(instant - timedelta(hours=2), instant)
        following = booking(instant, instant + timedelta(hours=2))
        item.reservation = source
        item.save()
        Event.objects.create(intervention=item, stage=6, occurred_at=instant - timedelta(hours=1),
                             original_at=instant - timedelta(hours=1), recorded_by=user)
        barrier = Barrier(2)
        def check(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return bool(relocate_next_reservation(item.pk, instant + timedelta(minutes=10)))
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(check, range(2))), [True, False])
        following.refresh_from_db()
        self.assertEqual(following.room, target)
        self.assertEqual(AutomaticRelocation.objects.count(), 1)
