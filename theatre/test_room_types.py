from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Reservation, Room
from .scheduling import availability, day_slots, reserve_hours
from .tests import fixtures
from .weekly_scheduling import find_available_rooms, reserve_continuous, reservation_revision, reschedule_reservation


class RoomTypeTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.emergency = Room.objects.create(name='Urgencias', room_type=Room.Type.EMERGENCY)
        self.day = timezone.localdate() + timedelta(days=7)

    def reserve(self, user=None, room=None, **kwargs):
        return reserve_continuous(user=user or self.user, room=room or self.emergency, day=self.day,
            desired_time=time(9, 30), duration_minutes=90, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio urgencias', patient_rut='12345678-5', **kwargs)

    def test_admin_dropdown_has_three_types_and_existing_default_major(self):
        self.assertEqual(self.item.room.room_type, Room.Type.MAJOR)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:theatre_room_add'))
        for label in ['Pabellón Urgencias', 'Pabellón Cirugías Mayores', 'Pabellón Cirugías Menores']:
            self.assertContains(response, label)

    def test_manual_reservations_require_administrator_and_superuser_can_book(self):
        with self.assertRaises(ValidationError):
            self.reserve()
        self.assertEqual(self.reserve(user=self.admin).room, self.emergency)
        other = Room.objects.create(name='Otra urgencia', room_type=Room.Type.EMERGENCY)
        root = get_user_model().objects.create_superuser(username='root-test', password='test-only')
        self.assertEqual(self.reserve(user=root, room=other).room, other)
        staff = get_user_model().objects.create_user(username='staff-test', is_staff=True)
        staff.groups.set(self.user.groups.all())
        with self.assertRaises(ValidationError):
            self.reserve(user=staff, room=other)

    def test_hourly_service_and_cells_enforce_profile(self):
        slot = next(s for s in day_slots(self.day) if timezone.localtime(s['start']).time() == time(9))
        args = dict(day=self.day, selections=[f'{self.emergency.pk}:{slot["index"]}'],
                    doctor=self.item.doctor, procedure=self.item.procedure,
                    patient_name='Paciente ficticio hora', patient_rut='12345678-5')
        with self.assertRaises(ValidationError):
            reserve_hours(user=self.user, **args)
        for user, expected in [(self.user, False), (self.admin, True)]:
            row = next(r for r in availability(self.day, user=user)['rows'] if r['room'] == self.emergency)
            self.assertEqual(row['slots'][slot['index']]['selectable'], expected)
        reserve_hours(user=self.admin, **args)

    def test_automatic_search_and_save_never_use_emergency_even_for_admin(self):
        found = find_available_rooms(day=self.day, desired_time=time(9, 30), duration_minutes=90)
        self.assertNotIn(self.emergency, found['rooms'])
        for actor in [self.user, self.admin]:
            with self.assertRaises(ValidationError):
                self.reserve(user=actor, automatic=True)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_reschedule_cannot_move_into_emergency_for_operator(self):
        booking = self.reserve(room=self.item.room)
        args = dict(reservation_id=booking.pk, room=self.emergency, day=self.day,
                    desired_time=time(11), expected_revision=reservation_revision(booking))
        with self.assertRaises(ValidationError):
            reschedule_reservation(user=self.user, **args)
        moved = reschedule_reservation(user=self.admin, **args)
        with self.assertRaises(ValidationError):
            reschedule_reservation(user=self.user, reservation_id=moved.pk, room=self.item.room,
                day=self.day, desired_time=time(13), expected_revision=reservation_revision(moved))

    def test_daily_form_and_forged_post_block_operator_but_admin_can_book(self):
        url = reverse('weekly_day', args=[self.emergency.pk, self.day.isoformat()])
        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), 'Solo el perfil Administrador')
        data = dict(doctor=self.item.doctor_id, procedure=self.item.procedure_id,
                    patient_name='Paciente ficticio intento', patient_rut='12345678-5',
                    desired_time='09:30', duration_minutes=90)
        self.client.post(url, data)
        self.assertFalse(Reservation.objects.exists())
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(url, data), url)

    def test_regular_types_remain_available(self):
        minor = Room.objects.create(name='Menores', room_type=Room.Type.MINOR)
        self.assertEqual(self.reserve(room=minor).room, minor)
