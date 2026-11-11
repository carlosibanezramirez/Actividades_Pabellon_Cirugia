from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Event, Reservation
from .occupancy_summary import active_reservations_for_day
from .scheduling import occupancy
from .services import record_event
from .tests import fixtures
from .weekly_scheduling import continuous_day, reschedule_reservation, reservation_revision


class ExitAdjustmentTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=7)
        self.booking = self.make_booking(time(9), time(11))
        self.item.reservation = self.booking
        self.item.save()
        for stage in range(1, 9):
            at = self.at(time(9)) + timedelta(minutes=stage)
            Event.objects.create(intervention=self.item, stage=stage, occurred_at=at, original_at=at, recorded_by=self.user)

    def at(self, clock, day=None):
        return timezone.make_aware(datetime.combine(day or self.day, clock))

    def make_booking(self, start, end, day=None):
        start_at = self.at(start, day)
        return Reservation.objects.create(room=self.item.room, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio ajuste', patient_rut='12345678-5', starts_at=start_at,
            planned_start_at=start_at + timedelta(minutes=15), ends_at=self.at(end, day), created_by=self.user)

    def exit(self, clock):
        with patch('theatre.services.timezone.now', return_value=self.at(clock)):
            record_event(user=self.user, intervention_id=self.item.pk, stage=9)
        self.booking.refresh_from_db()

    def test_early_exit_shortens_reservation_and_frees_remainder(self):
        self.exit(time(10))
        self.assertEqual(self.booking.ends_at, self.at(time(10)))
        self.assertEqual(self.booking.original_ends_at, self.at(time(11)))
        self.assertTrue(self.booking.timing_adjusted)
        self.assertEqual(self.booking.adjustments.count(), 1)
        _, periods = occupancy(self.day, now=self.at(time(10)))
        self.assertTrue(all(p['end'] <= self.at(time(10)) for p in periods))

    def test_very_short_legacy_use_is_released_without_one_hour_minimum(self):
        self.booking.planned_start_at = None
        self.booking.save()
        self.exit(time(9, 10))
        _, periods = occupancy(self.day, now=self.at(time(9, 10)))
        self.assertTrue(all(p['end'] <= self.at(time(9, 10)) for p in periods))
        self.assertEqual(self.booking.ends_at, self.at(time(9, 10)))

    def test_exit_before_original_start_keeps_actual_occupied_interval(self):
        for event in self.item.events.all():
            event.occurred_at = self.at(time(8, 30)) + timedelta(minutes=event.stage)
            event.save()
        self.exit(time(8, 45))
        self.assertEqual(self.booking.starts_at, self.at(time(8, 31)))
        self.assertEqual(self.booking.ends_at, self.at(time(8, 45)))
        self.assertEqual(self.booking.planned_start_at, self.at(time(8, 33)))

    def test_on_time_does_not_create_spurious_adjustment(self):
        self.exit(time(11))
        self.assertFalse(self.booking.timing_adjusted)
        self.assertEqual(self.booking.adjustments.count(), 0)

    def test_late_exit_in_free_time_extends_without_brown(self):
        self.exit(time(11, 30))
        self.assertEqual(self.booking.ends_at, self.at(time(11, 30)))
        self.assertIsNone(self.booking.overrun_from)
        self.assertFalse(any(part.get('overrun') for b in continuous_day(self.item.room, self.day)['booking_blocks'] for part in b['parts']))

    def test_conflict_extends_in_brown_and_shortens_next_reservation_at_start(self):
        next_booking = self.make_booking(time(11), time(13))
        self.exit(time(11, 30))
        next_booking.refresh_from_db()
        self.assertEqual(next_booking.starts_at, self.at(time(11, 30)))
        self.assertEqual(next_booking.planned_start_at, self.at(time(11, 45)))
        self.assertEqual(next_booking.ends_at, self.at(time(13)))
        self.assertEqual(next_booking.planned_duration_minutes, 75)
        self.assertFalse(next_booking.needs_rescheduling)
        self.assertEqual(self.booking.overrun_from, self.at(time(11)))
        block = next(b for b in continuous_day(self.item.room, self.day)['booking_blocks'] if b['booking'].pk == self.booking.pk)
        brown = [p for p in block['parts'] if p.get('overrun')]
        self.assertEqual([(p['start'], p['end']) for p in brown], [(self.at(time(11)), self.at(time(11, 30)))])

    def test_fully_consumed_following_bookings_wait_for_reprogramming_not_cancelled(self):
        next_booking = self.make_booking(time(11), time(11, 20))
        after = self.make_booking(time(11, 20), time(13))
        self.exit(time(11, 45))
        next_booking.refresh_from_db()
        after.refresh_from_db()
        self.assertTrue(next_booking.needs_rescheduling)
        self.assertIsNone(next_booking.cancelled_at)
        self.assertEqual(next_booking.starts_at, next_booking.ends_at)
        self.assertEqual(after.starts_at, self.at(time(11, 45)))
        self.assertNotIn(next_booking, active_reservations_for_day(self.item.room, self.day))
        self.assertIn(next_booking, list(continuous_day(self.item.room, self.day)['displaced_bookings']))
        restored = reschedule_reservation(user=self.user, reservation_id=next_booking.pk, room=self.item.room,
            day=self.day + timedelta(days=1), desired_time=time(9), expected_revision=reservation_revision(next_booking))
        self.assertFalse(restored.needs_rescheduling)
        self.assertEqual(restored.preparation_minutes, 15)
        self.assertEqual(restored.planned_duration_minutes, 5)
        self.assertEqual(restored.adjustments.count(), 1)

    def test_cancelled_following_reservation_does_not_make_brown_extension(self):
        next_booking = self.make_booking(time(11), time(13))
        next_booking.cancelled_at = timezone.now()
        next_booking.save()
        self.exit(time(11, 30))
        self.assertIsNone(self.booking.overrun_from)

    def test_overnight_conflict_is_clipped_on_next_day(self):
        self.booking.ends_at = self.at(time(23))
        self.booking.save()
        next_day = self.day + timedelta(days=1)
        following = self.make_booking(time(0), time(2), day=next_day)
        with patch('theatre.services.timezone.now', return_value=self.at(time(0, 30), next_day)):
            record_event(user=self.user, intervention_id=self.item.pk, stage=9)
        following.refresh_from_db()
        self.assertEqual(following.starts_at, self.at(time(0, 30), next_day))
        block = next(b for b in continuous_day(self.item.room, next_day)['booking_blocks'] if b['booking'].pk == self.booking.pk)
        self.assertTrue(block['parts'][0]['overrun'])
        self.assertEqual(block['parts'][0]['end'], self.at(time(0, 30), next_day))
