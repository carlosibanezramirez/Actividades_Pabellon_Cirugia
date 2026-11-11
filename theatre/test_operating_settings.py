from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .alarms import preparation_alarm
from .dashboard import room_board
from .models import Event, OperatingSettings
from .scheduling import availability, day_slots, reserve_hours
from .tests import fixtures
from .weekly_scheduling import available_starts, continuous_day, reserve_continuous


class OperatingSettingsTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.item = fixtures()
        self.policy = OperatingSettings.current()
        self.day = timezone.localdate() + timedelta(days=4)
        self.client.force_login(self.user)

    def reserve(self, clock=time(9, 30), minutes=90, day=None):
        return reserve_continuous(user=self.user, room=self.item.room, day=day or self.day,
                                  desired_time=clock, duration_minutes=minutes,
                                  doctor=self.item.doctor, procedure=self.item.procedure,
                                  patient_name='Paciente ficticio configuración', patient_rut='12345678-5')

    def test_default_configuration_and_admin_permissions(self):
        self.assertEqual((self.policy.preparation_mean_minutes, self.policy.preparation_max_minutes), (15, 30))
        self.assertEqual((self.item.room.opening_time, self.item.room.closing_time), (time(7), time(23)))
        self.assertFalse(self.user.has_perm('theatre.change_operatingsettings'))
        self.assertTrue(self.administrator.has_perm('theatre.change_operatingsettings'))
        self.client.force_login(self.administrator)
        url = reverse('admin:theatre_operatingsettings_change', args=[1])
        response = self.client.post(url, {'preparation_mean_minutes': 20, 'preparation_max_minutes': 40, 'allowed_overrun_minutes': 10,
                                          '_save': 'Guardar'})
        self.assertEqual(response.status_code, 302)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.preparation_mean_minutes, 20)
        room_url = reverse('admin:theatre_room_change', args=[self.item.room_id])
        response = self.client.post(room_url, {'name': self.item.room.name, 'room_type': self.item.room.room_type, 'active': 'on',
                                               'opening_time': '08:00', 'closing_time': '22:00', '_save': 'Guardar'})
        self.assertEqual(response.status_code, 302)
        self.item.room.refresh_from_db()
        self.assertEqual(self.item.room.opening_time, time(8))

    def test_configuration_rejects_inverted_hours_and_invalid_thresholds(self):
        self.policy.preparation_mean_minutes = 20
        self.policy.preparation_max_minutes = 10
        with self.assertRaises(ValidationError):
            self.policy.full_clean()
        self.policy.preparation_max_minutes = 30
        self.item.room.closing_time = time(6)
        with self.assertRaises(ValidationError):
            self.item.room.full_clean()
        self.item.room.closing_time = time(23, 0, 1)
        with self.assertRaises(ValidationError):
            self.item.room.full_clean()

    def test_changed_preparation_affects_new_reservations_only(self):
        old = self.reserve()
        self.policy.preparation_mean_minutes = 20
        self.policy.save()
        new = self.reserve(day=self.day + timedelta(days=1))
        old.refresh_from_db()
        self.assertEqual(old.preparation_minutes, 15)
        self.assertEqual(new.preparation_minutes, 20)
        self.assertEqual(timezone.localtime(new.starts_at).time(), time(9, 10))
        block = continuous_day(self.item.room, self.day + timedelta(days=1))['booking_blocks'][0]
        self.assertEqual(block['total_duration_minutes'], 110)

    def test_first_start_at_opening_includes_preparation_before_opening(self):
        self.policy.preparation_mean_minutes = 20
        self.policy.save()
        options = available_starts(self.item.room, self.day)
        self.assertEqual(options[0]['value'], '07:00')
        booking = self.reserve(time(7), 60)
        self.assertEqual(timezone.localtime(booking.starts_at).time(), time(6, 40))
        day = continuous_day(self.item.room, self.day)
        self.assertEqual(timezone.localtime(day['segments'][0]['end']).time(), time(6, 40))
        self.assertTrue(day['segments'][0]['closed'])
        self.assertTrue(day['booking_blocks'][0]['parts'][0]['preparation'])

    def test_opening_and_closing_enforced_at_service_and_selector(self):
        with self.assertRaises(ValidationError):
            self.reserve(time(6, 30), 60)
        with self.assertRaises(ValidationError):
            self.reserve(time(23, 30), 1)
        values = [option['value'] for option in available_starts(self.item.room, self.day)]
        self.assertNotIn('06:30', values)
        self.assertIn('23:00', values)
        self.assertNotIn('23:30', values)
        booking = self.reserve(time(23), 180)
        self.assertEqual(timezone.localtime(booking.ends_at).time(), time(2))
        self.assertEqual(timezone.localtime(booking.ends_at).date(), self.day + timedelta(days=1))

    def test_closed_segments_remain_visible_and_are_not_bookable_links(self):
        day = continuous_day(self.item.room, self.day)
        self.assertEqual([segment['closed'] for segment in day['segments']], [True, False, True])
        self.assertEqual(timezone.localtime(day['segments'][0]['end']).time(), time(7))
        self.assertEqual(timezone.localtime(day['segments'][-1]['start']).time(), time(23))
        self.assertEqual(sum((s['end'] - s['start']).total_seconds() for s in day['segments']), 86400)
        response = self.client.get(reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()]))
        self.assertContains(response, 'continuous-span closed', count=2)
        self.assertContains(response, 'Fuera de horario')

    def test_hourly_agenda_also_blocks_outside_configured_hours(self):
        cells = availability(self.day)['rows'][0]['slots']
        six = next(cell for cell in cells if timezone.localtime(cell['start']).time() == time(6))
        self.assertFalse(six['selectable'])
        self.assertEqual(six['state'], 'fuera_horario')
        with self.assertRaises(ValidationError):
            reserve_hours(user=self.user, day=self.day, selections=[six['value']],
                          doctor=self.item.doctor, procedure=self.item.procedure,
                          patient_name='Paciente ficticio horario', patient_rut='12345678-5')

    def test_alarm_threshold_is_strictly_exceeded_not_equal(self):
        now = timezone.now()
        exact = preparation_alarm(self.item.room_id, self.item.pk, now - timedelta(minutes=30), 1, 30, now)
        self.assertFalse(exact['exceeded'])
        exceeded = preparation_alarm(self.item.room_id, self.item.pk, now - timedelta(minutes=30, seconds=1), 1, 30, now)
        self.assertTrue(exceeded['exceeded'])

    def test_alarm_api_and_cards_stop_after_preparation_ends(self):
        started = timezone.now() - timedelta(minutes=31)
        Event.objects.create(intervention=self.item, stage=1, occurred_at=started,
                             original_at=started, recorded_by=self.user)
        self.assertTrue(room_board()[0]['alarm']['exceeded'])
        status_url = reverse('preparation_status')
        data = self.client.get(status_url).json()
        self.assertEqual(data['active'][0]['room_id'], self.item.room_id)
        self.assertEqual(data['maximum_minutes'], 30)
        response = self.client.get(reverse('detail', args=[self.item.pk]))
        self.assertContains(response, 'Tiempo máximo de preparación excedido')
        Event.objects.create(intervention=self.item, stage=2, occurred_at=timezone.now(),
                             original_at=timezone.now(), recorded_by=self.user)
        self.assertFalse(room_board()[0]['alarm']['active'])
        self.assertEqual(self.client.get(status_url).json()['active'], [])

    def test_alarm_respects_changed_maximum_and_protects_endpoint(self):
        started = timezone.now() - timedelta(minutes=31)
        Event.objects.create(intervention=self.item, stage=1, occurred_at=started,
                             original_at=started, recorded_by=self.user)
        self.policy.preparation_max_minutes = 45
        self.policy.save()
        self.assertFalse(room_board()[0]['alarm']['exceeded'])
        self.assertEqual(self.client.get(reverse('preparation_status')).json()['maximum_minutes'], 45)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('preparation_status')).status_code, 302)
