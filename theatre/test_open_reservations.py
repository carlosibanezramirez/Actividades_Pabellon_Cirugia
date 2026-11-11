from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Intervention, Reservation
from .tests import fixtures


class OpenReservationTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.item.completed_at = timezone.now()
        self.item.save()
        now = timezone.now()
        self.booking = Reservation.objects.create(room=self.item.room, procedure=self.item.procedure,
            doctor=self.item.doctor, patient_name='Paciente ficticio apertura', patient_rut='12345678-5',
            diagnosis='Diagnóstico ficticio apertura', starts_at=now - timedelta(minutes=15),
            planned_start_at=now, ends_at=now + timedelta(hours=1), created_by=self.user)
        self.url = reverse('open_reservation', args=[self.booking.pk])
        self.client.force_login(self.user)

    def test_list_filters_reservation_and_excludes_cancelled(self):
        url = reverse('open_reservations')
        response = self.client.get(url)
        self.assertContains(response, self.booking.patient_name)
        self.assertContains(response, 'Disponible para iniciar')
        self.assertContains(response, f'href="{self.url}"')
        response = self.client.get(url, {'fecha': timezone.localdate().isoformat(), 'search': '12.345.678-5'})
        self.assertContains(response, self.booking.patient_name)
        response = self.client.get(url, {'fecha': timezone.localdate().isoformat(), 'search': 'No existe'})
        self.assertContains(response, 'No hay reservas confirmadas')
        self.booking.cancelled_at = timezone.now()
        self.booking.save()
        self.assertNotContains(self.client.get(url), self.booking.patient_name)

    def test_get_only_reviews_post_opens_without_recording_events(self):
        before = Intervention.objects.count()
        response = self.client.get(self.url)
        self.assertContains(response, 'Comenzar registro de eventos')
        self.assertContains(response, self.booking.diagnosis)
        self.assertEqual(Intervention.objects.count(), before)
        response = self.client.post(self.url, {'anesthetist': self.item.anesthetist_id,
                                             'room': 99999, 'doctor': 99999, 'reservation': 99999})
        item = Intervention.objects.get(reservation=self.booking)
        self.assertRedirects(response, reverse('detail', args=[item.pk]) + '#pending-activities')
        self.assertEqual(item.room, self.booking.room)
        self.assertEqual(item.doctor, self.booking.doctor)
        self.assertEqual(item.procedure, self.booking.procedure)
        self.assertEqual(item.anesthetist, self.item.anesthetist)
        self.assertEqual(item.events.count(), 0)
        self.assertEqual(item.preoperative_activities.count(), 0)
        self.assertRedirects(self.client.get(self.url), reverse('detail', args=[item.pk]))
        self.client.post(self.url, {'anesthetist': self.item.anesthetist_id})
        self.assertEqual(Intervention.objects.filter(reservation=self.booking).count(), 1)
        self.assertContains(self.client.get(reverse('open_reservations')), 'Retomar intervención')

    def test_valid_anesthetist_required(self):
        self.assertContains(self.client.post(self.url, {}), 'Este campo es obligatorio')
        self.client.post(self.url, {'anesthetist': self.item.doctor_id})
        self.assertFalse(Intervention.objects.filter(reservation=self.booking).exists())

    def test_future_expired_cancelled_and_occupied_cannot_start(self):
        original = (self.booking.starts_at, self.booking.planned_start_at, self.booking.ends_at)
        for shift in [timedelta(days=1), -timedelta(days=1)]:
            self.booking.starts_at, self.booking.planned_start_at, self.booking.ends_at = [value + shift for value in original]
            self.booking.save()
            self.assertNotContains(self.client.get(self.url), 'Comenzar registro de eventos')
            self.client.post(self.url, {'anesthetist': self.item.anesthetist_id})
            self.assertFalse(Intervention.objects.filter(reservation=self.booking).exists())
        self.booking.starts_at, self.booking.planned_start_at, self.booking.ends_at = original
        self.booking.cancelled_at = timezone.now()
        self.booking.save()
        self.assertContains(self.client.get(self.url), 'reserva está cancelada')
        self.client.post(self.url, {'anesthetist': self.item.anesthetist_id})
        self.assertFalse(Intervention.objects.filter(reservation=self.booking).exists())
        self.booking.cancelled_at = None
        self.booking.save()
        self.item.completed_at = None
        self.item.save()
        self.client.post(self.url, {'anesthetist': self.item.anesthetist_id})
        self.assertFalse(Intervention.objects.filter(reservation=self.booking).exists())

    def test_permissions_and_invalid_filters(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        outsider = get_user_model().objects.create_user(username='sin-abrir-reserva')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {'anesthetist': self.item.anesthetist_id}).status_code, 403)
        self.assertEqual(self.client.get(reverse('open_reservations')).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(reverse('open_reservations'), {'fecha': 'invalida'})
        self.assertTrue(response.context['form'].errors)
