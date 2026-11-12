from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Doctor, Reservation
from .tests import fixtures


class DoctorAgendaTests(TestCase):
    def setUp(self):
        self.operator, self.admin, self.item = fixtures()
        self.user = get_user_model().objects.create_user(username='medico-test', password='doctor-test-password', email='doctor@example.test')
        self.user.groups.add(Group.objects.get(name='Médico'))
        self.doctor = self.item.doctor
        self.doctor.user = self.user
        self.doctor.save()
        self.day = timezone.localdate() + timedelta(days=2)
        self.start = timezone.make_aware(datetime.combine(self.day, time(9)))
        self.booking = self.book(self.doctor, 'Paciente propio ficticio')
        other = Doctor.objects.create(name='Otro médico')
        self.foreign = self.book(other, 'Paciente ajeno confidencial')
        self.client.force_login(self.user)

    def book(self, doctor, patient):
        return Reservation.objects.create(room=self.item.room, doctor=doctor, procedure=self.item.procedure,
            starts_at=self.start, planned_start_at=self.start + timedelta(minutes=15),
            ends_at=self.start + timedelta(hours=2), patient_name=patient, patient_rut='12345678-5', created_by=self.operator)

    def test_login_redirect_and_week_only_include_own_reservations(self):
        self.assertRedirects(self.client.get(reverse('account_home')), reverse('doctor_agenda'))
        response = self.client.get(reverse('doctor_agenda'), {'fecha': self.day.isoformat(), 'doctor': self.foreign.doctor_id})
        self.assertContains(response, self.booking.patient_name)
        self.assertNotContains(response, self.foreign.patient_name)
        self.assertNotContains(response, '>Nueva reserva</a>')
        self.assertNotContains(response, '>Abrir reserva</a>')
        self.assertEqual(len(response.context['days']), 7)
        self.assertEqual(response.context['monday'].weekday(), 0)
        self.assertEqual(response.context['sunday'].weekday(), 6)

    def test_ownership_required_for_details_and_notification_links(self):
        self.assertEqual(self.client.get(reverse('doctor_reservation', args=[self.booking.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('doctor_reservation', args=[self.foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('notification_reservation', args=[self.foreign.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse('notification_reservation', args=[self.booking.pk])),
                             reverse('doctor_reservation', args=[self.booking.pk]))
        self.assertEqual(self.client.get(reverse('reservation_detail', args=[self.foreign.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse('reservation_detail', args=[self.booking.pk])),
                             reverse('doctor_reservation', args=[self.booking.pk]))
        self.assertEqual(self.client.get(reverse('interventions')).status_code, 403)
        self.assertEqual(self.client.post(reverse('reservation_cancel', args=[self.foreign.pk]), {}).status_code, 403)

    def test_own_intervention_is_read_only_and_cancelled_reservations_remain_visible(self):
        response = self.client.get(reverse('doctor_intervention', args=[self.item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Registrar evento')
        self.assertNotContains(response, 'Corregir hora')
        self.booking.cancelled_at = timezone.now()
        self.booking.save()
        self.assertContains(self.client.get(reverse('doctor_agenda'), {'fecha': self.day.isoformat()}), 'Cancelada')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('doctor_intervention', args=[self.item.pk])).status_code, 403)

    def test_inactive_or_unlinked_doctor_and_invalid_date(self):
        self.doctor.active = False
        self.doctor.save()
        self.assertEqual(self.client.get(reverse('doctor_agenda')).status_code, 404)
        self.doctor.active = True
        self.doctor.save()
        response = self.client.get(reverse('doctor_agenda'), {'fecha': 'incorrecta'})
        self.assertTrue(response.context['form'].errors)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('doctor_agenda')).status_code, 302)

    def test_admin_link_assigns_medical_profile(self):
        user = get_user_model().objects.create_user(username='nuevo-medico')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin:theatre_doctor_change', args=[self.doctor.pk]),
            {'name': self.doctor.name, 'email': 'new@example.test', 'active': 'on', 'user': user.pk})
        self.assertEqual(response.status_code, 302)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.user, user)
        self.assertTrue(user.groups.filter(name='Médico').exists())
        self.assertFalse(self.user.groups.filter(name='Médico').exists())

    def test_superuser_without_doctor_record_keeps_operations_home(self):
        root = get_user_model().objects.create_superuser(username='root-doctor-test', password='test-only')
        self.client.force_login(root)
        self.assertRedirects(self.client.get(reverse('account_home')), reverse('interventions'))
