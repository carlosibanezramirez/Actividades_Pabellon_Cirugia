from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Reservation

from .scheduling import day_slots, reserve_hours
from .tests import fixtures
from .weekly_scheduling import available_starts, continuous_day, reserve_continuous


class StartGapTests(TestCase):
    def setUp(self):
        self.user, _, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=4)
        self.client.force_login(self.user)

    def reserve(self, clock=time(9, 30), minutes=90, day=None):
        return reserve_continuous(user=self.user, room=self.item.room, day=day or self.day,
                                  desired_time=clock, duration_minutes=minutes,
                                  doctor=self.item.doctor, procedure=self.item.procedure,
                                  patient_name='Paciente ficticio continuidad', patient_rut='12345678-5')

    def test_free_area_after_end_suggests_closest_half_hour_with_preparation(self):
        booking = self.reserve()  # 09:15–11:00
        day = continuous_day(self.item.room, self.day)
        gap = next(s for s in day['segments'] if not s['busy'] and s['start'] == booking.ends_at)
        self.assertEqual(gap['suggested_time'], '11:30')
        after = [option['value'] for option in day['start_options'] if option['planned'] >= booking.ends_at]
        self.assertEqual(after, ['11:30'])
        response = self.client.get(reverse('weekly_agenda'), {'room': self.item.room_id, 'fecha': self.day.isoformat()})
        self.assertContains(response, '?inicio=11%3A30#continuous-reservation-form')

    def test_suggestion_prefills_form_and_later_options_are_not_offered(self):
        self.reserve()
        response = self.client.get(reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()]), {'inicio': '11:30'})
        self.assertEqual(response.context['form'].initial['desired_time'], '11:30')
        values = [value for value, label in response.context['form'].fields['desired_time'].widget.choices]
        self.assertIn('11:30', values)
        self.assertNotIn('12:00', values)

    def test_thirty_minutes_is_inclusive_and_further_start_is_rejected_by_service(self):
        self.reserve()
        with self.assertRaises(ValidationError):
            self.reserve(time(12), 20)
        following = self.reserve(time(11, 30), 20)
        self.assertEqual(timezone.localtime(following.starts_at).time(), time(11, 15))

    def test_no_compatible_half_hour_is_reported_without_shortening_preparation(self):
        booking = self.reserve(minutes=110)  # termina 11:20
        options = available_starts(self.item.room, self.day)
        self.assertFalse([option for option in options if option['planned'] >= booking.ends_at])
        with self.assertRaises(ValidationError):
            self.reserve(time(11, 30), 20)  # preparación a las 11:15 se superpone
        with self.assertRaises(ValidationError):
            self.reserve(time(12), 20)  # 40 minutos desde el término
        day = continuous_day(self.item.room, self.day)
        gap = next(s for s in day['segments'] if not s['busy'] and s['start'] == booking.ends_at)
        self.assertFalse(gap['has_start'])
        response = self.client.get(reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()]), {'sin_inicio': '1'})
        self.assertContains(response, 'El tramo libre seleccionado no tiene un inicio compatible')

    def test_first_booking_of_another_day_does_not_inherit_previous_day_gap(self):
        self.reserve()
        booking = self.reserve(time(15), 20, day=self.day + timedelta(days=1))
        self.assertEqual(timezone.localtime(booking.planned_start_at).time(), time(15))

    def test_midnight_continuation_checks_previous_booking_ending_in_selected_day(self):
        policy = self.item.room
        policy.opening_time = time(0)
        policy.closing_time = time(23, 59)
        policy.save()
        planned = timezone.make_aware(datetime.combine(self.day - timedelta(days=1), time(23, 30)))
        previous = Reservation.objects.create(room=self.item.room, doctor=self.item.doctor,
                                              procedure=self.item.procedure, patient_name='Paciente ficticio histórico',
                                              starts_at=planned - timedelta(minutes=15), planned_start_at=planned,
                                              ends_at=planned + timedelta(minutes=40), created_by=self.user)
        self.assertEqual(timezone.localtime(previous.ends_at).time(), time(0, 10))
        with self.assertRaises(ValidationError):
            self.reserve(time(1), 20)
        self.reserve(time(0, 30), 20)

    def test_hourly_agenda_cannot_bypass_the_maximum_gap(self):
        self.reserve()
        noon = next(s for s in day_slots(self.day) if timezone.localtime(s['start']).time() == time(12))
        with self.assertRaises(ValidationError):
            reserve_hours(user=self.user, day=self.day, selections=[f'{self.item.room_id}:{noon["index"]}'],
                          doctor=self.item.doctor, procedure=self.item.procedure,
                          patient_name='Paciente ficticio horario', patient_rut='12345678-5')

    def test_tampered_post_and_stale_suggestion_do_not_offer_invalid_times(self):
        self.reserve()
        url = reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()])
        response = self.client.post(url, {
            'doctor': self.item.doctor_id, 'procedure': self.item.procedure_id,
            'patient_name': 'Paciente ficticio', 'patient_rut': '12345678-5',
            'desired_time': '12:00', 'duration_minutes': '20',
        })
        self.assertIn('desired_time', response.context['form'].errors)
        response = self.client.get(url, {'inicio': '12:00'})
        self.assertTrue(response.context['suggestion_expired'])
        self.assertEqual(response.context['form'].initial, {})
