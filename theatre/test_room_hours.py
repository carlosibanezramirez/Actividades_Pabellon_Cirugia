from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import OperatingSettings, Room
from .scheduling import availability
from .tests import fixtures
from .weekly_scheduling import available_starts, continuous_day, reserve_continuous


class RoomHoursTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.item = fixtures()
        self.room = self.item.room
        self.room.opening_time = time(6)
        self.room.closing_time = time(23)
        self.room.save()
        self.other = Room.objects.create(name='Segundo pabellón', opening_time=time(9), closing_time=time(18))
        self.day = timezone.localdate() + timedelta(days=4)
        self.client.force_login(self.administrator)

    def reserve(self, room, clock, minutes):
        return reserve_continuous(user=self.user, room=room, day=self.day, desired_time=clock,
                                  duration_minutes=minutes, doctor=self.item.doctor,
                                  procedure=self.item.procedure, patient_name='Paciente ficticio horario individual',
                                  patient_rut='12345678-5')

    def test_each_room_has_its_own_selector_closed_band_and_reservation_limits(self):
        self.assertEqual(available_starts(self.room, self.day)[0]['value'], '06:00')
        self.assertEqual(available_starts(self.other, self.day)[0]['value'], '09:00')
        self.assertEqual(continuous_day(self.room, self.day)['free_minutes'], 17 * 60)
        self.assertEqual(continuous_day(self.other, self.day)['free_minutes'], 9 * 60)
        rows = {row['room'].pk: row for row in availability(self.day)['rows']}
        at_six = lambda row: next(cell for cell in row['slots'] if timezone.localtime(cell['start']).time() == time(6))
        self.assertTrue(at_six(rows[self.room.pk])['selectable'])
        self.assertFalse(at_six(rows[self.other.pk])['selectable'])
        self.reserve(self.room, time(6), 60)
        with self.assertRaises(ValidationError):
            self.reserve(self.other, time(6), 60)
        with self.assertRaises(ValidationError):
            self.reserve(self.other, time(18, 30), 31)
        self.reserve(self.other, time(17, 30), 30)

    def test_admin_room_form_has_hours_and_global_preparation_form_does_not(self):
        response = self.client.get(reverse('admin:theatre_room_add'))
        self.assertContains(response, 'name="opening_time"')
        self.assertContains(response, 'name="closing_time"')
        response = self.client.get(reverse('admin:theatre_room_change', args=[self.other.pk]))
        self.assertContains(response, 'value="09:00"')
        response = self.client.get(reverse('admin:theatre_operatingsettings_change', args=[OperatingSettings.current().pk]))
        self.assertNotContains(response, 'name="opening_time"')
        self.assertNotContains(response, 'name="closing_time"')

    def test_weekly_comment_removed_and_daily_note_uses_selected_room_hours(self):
        response = self.client.get(reverse('weekly_agenda'), {'room': self.other.pk, 'fecha': self.day.isoformat()})
        self.assertNotContains(response, 'La preparación previa se muestra en negro;')
        self.assertNotContains(response, 'No hay bloques horarios predefinidos.')
        self.assertNotContains(response, 'Horario de reservas:')
        response = self.client.get(reverse('weekly_day', args=[self.other.pk, self.day.isoformat()]))
        self.assertContains(response, '09:00')
        self.assertContains(response, '18:00')

    def test_changing_one_room_does_not_modify_another(self):
        self.other.opening_time = time(10)
        self.other.closing_time = time(17)
        self.other.full_clean()
        self.other.save()
        self.room.refresh_from_db()
        self.assertEqual(self.room.opening_time, time(6))
        self.assertEqual(self.room.closing_time, time(23))
        self.assertEqual(available_starts(self.other, self.day)[0]['value'], '10:00')
