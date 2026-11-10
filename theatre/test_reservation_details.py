from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ContinuousReservationForm, ReservationRequestForm
from .models import Reservation
from .rut import normalize_rut
from .tests import fixtures
from .weekly_scheduling import continuous_day, reserve_continuous


class ReservationDetailsTests(TestCase):
    def setUp(self):
        self.user, _, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=4)
        self.client.force_login(self.user)

    def reserve(self, **overrides):
        args = dict(user=self.user, room=self.item.room, day=self.day, desired_time=time(9),
                    duration_minutes=45, doctor=self.item.doctor, procedure=self.item.procedure,
                    patient_name='Paciente ficticio <prueba>', patient_rut='12.345.678-5')
        args.update(overrides)
        return reserve_continuous(**args)

    def test_rut_normalization_and_check_digit(self):
        for value in ['12.345.678-5', '12345678-5', '123456785']:
            self.assertEqual(normalize_rut(value), '12345678-5')
        self.assertEqual(normalize_rut('6-k'), '6-K')
        for value in ['', '12345678-9', '0-0', '<script>', '1234567890-5']:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_rut(value)

    def test_new_reservations_require_valid_rut_at_form_and_service_levels(self):
        self.assertTrue(ContinuousReservationForm().fields['patient_rut'].required)
        self.assertTrue(ReservationRequestForm().fields['patient_rut'].required)
        with self.assertRaises(ValidationError):
            self.reserve(patient_rut='')
        with self.assertRaises(ValidationError):
            self.reserve(patient_rut='12345678-9')
        self.assertEqual(Reservation.objects.count(), 0)
        booking = self.reserve()
        self.assertEqual(booking.patient_rut, '12345678-5')

    def test_adjacent_reservations_keep_separate_text_blocks(self):
        first = self.reserve()  # 08:45–09:45
        second = self.reserve(desired_time=time(10))  # 09:45–10:45
        day = continuous_day(self.item.room, self.day)
        self.assertEqual(len([segment for segment in day['segments'] if segment['busy']]), 1)
        self.assertEqual([block['booking'].pk for block in day['booking_blocks']], [first.pk, second.pk])
        response = self.client.get(reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()]))
        self.assertContains(response, 'data-booking-tooltip', count=2)
        self.assertContains(response, self.item.procedure.name)
        self.assertContains(response, self.item.doctor.name)
        self.assertContains(response, '08:45 – 09:45')
        self.assertContains(response, 'data-rut="12345678-5"', count=2)
        self.assertContains(response, 'Paciente ficticio &lt;prueba&gt;')
        self.assertNotContains(response, 'Paciente ficticio <prueba>')

    def test_legacy_reservation_with_no_rut_remains_visible(self):
        example = self.reserve()
        Reservation.objects.filter(pk=example.pk).update(patient_rut='')
        response = self.client.get(reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()]))
        self.assertContains(response, 'data-rut="No registrado"')
        response = self.client.get(reverse('reservation_detail', args=[example.pk]))
        self.assertContains(response, 'RUT del paciente')
        self.assertContains(response, 'No registrado')

    def test_missing_rut_is_reported_and_rut_inputs_appear_in_both_reservation_views(self):
        url = reverse('weekly_day', args=[self.item.room_id, self.day.isoformat()])
        response = self.client.post(url, {
            'doctor': self.item.doctor_id, 'patient_name': 'Paciente ficticio',
            'procedure': self.item.procedure_id, 'desired_time': '09:00', 'duration_minutes': '45',
        })
        self.assertIn('patient_rut', response.context['form'].errors)
        self.assertEqual(Reservation.objects.count(), 0)
        self.assertContains(response, 'name="patient_rut"')
        response = self.client.get(reverse('agenda'), {'fecha': self.day.isoformat()})
        self.assertContains(response, 'name="patient_rut"')
