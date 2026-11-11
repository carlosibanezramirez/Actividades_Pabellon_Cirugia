from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CancellationReason, OperatingSettings, Reservation, Room
from .tests import fixtures
from .weekly_scheduling import cancel_reservation, find_available_rooms, reservation_revision, reserve_continuous


class ReservationSearchTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=7)
        self.other = Room.objects.create(name='Pabellón alternativo')
        Room.objects.create(name='Pabellón inactivo', active=False)
        self.client.force_login(self.user)
        self.url = reverse('reservation_search')
        self.data = dict(action='search', doctor=self.item.doctor_id, patient_name='Paciente ficticio búsqueda',
                         patient_rut='12.345.678-5', diagnosis='Diagnóstico ficticio de prueba',
                         procedure=self.item.procedure_id, fecha=self.day.isoformat(), desired_time='09:30',
                         duration_minutes=90)

    def reserve(self, room=None, clock=time(9, 30), duration=90, day=None):
        return reserve_continuous(user=self.user, room=room or self.other, day=day or self.day,
            desired_time=clock, duration_minutes=duration, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio ocupado', patient_rut='12345678-5')

    def search(self):
        return self.client.post(self.url, self.data)

    def choose(self, token, room=None):
        return self.client.post(self.url, {'action': 'choose', 'token': token, 'room': (room or self.other).pk})

    def test_three_steps_no_write_before_confirmation_and_diagnosis_persisted(self):
        result = self.search()
        self.assertEqual({r.pk for r in result.context['result']['rooms']}, {self.item.room_id, self.other.pk})
        self.assertEqual(Reservation.objects.count(), 0)
        review = self.choose(result.context['token'])
        self.assertContains(review, 'Confirmar reserva')
        self.assertContains(review, self.data['diagnosis'])
        self.assertContains(review, '09:15')
        self.assertContains(review, '09:30')
        self.assertContains(review, '11:00')
        self.assertEqual(Reservation.objects.count(), 0)
        confirmation = review.context['token']
        response = self.client.post(self.url, {'action': 'confirm', 'token': confirmation, 'room': self.item.room_id,
                                               'patient_name': 'Dato manipulado', 'diagnosis': 'Manipulado'})
        booking = Reservation.objects.get()
        self.assertRedirects(response, reverse('reservation_detail', args=[booking.pk]))
        self.assertEqual(booking.room, self.other)
        self.assertEqual(booking.diagnosis, self.data['diagnosis'])
        self.assertEqual(booking.patient_name, self.data['patient_name'])
        self.assertEqual(booking.patient_rut, '12345678-5')
        self.assertEqual(booking.planned_duration_minutes, 90)
        self.assertEqual(booking.preparation_minutes, 15)
        self.assertContains(self.client.get(response.url), self.data['diagnosis'])
        self.client.post(self.url, {'action': 'confirm', 'token': confirmation})
        self.assertEqual(Reservation.objects.count(), 1)

    def test_full_duration_and_preparation_are_checked_and_cancelled_slots_are_free(self):
        conflict = self.reserve(clock=time(8), duration=80)  # termina 09:20; solapa preparación 09:15.
        result = self.search()
        self.assertNotIn(self.other, result.context['result']['rooms'])
        reason = CancellationReason.objects.create(name='Causa ficticia')
        cancel_reservation(user=self.user, reservation_id=conflict.pk, reason=reason,
                           expected_revision=reservation_revision(conflict))
        self.assertIn(self.other, self.search().context['result']['rooms'])

    def test_availability_is_rechecked_on_confirm(self):
        result = self.search()
        review = self.choose(result.context['token'])
        self.reserve()
        response = self.client.post(self.url, {'action': 'confirm', 'token': review.context['token']})
        self.assertContains(response, 'ya no está disponible')
        self.assertEqual(Reservation.objects.count(), 1)

    def test_preparation_change_requires_another_confirmation(self):
        review = self.choose(self.search().context['token'])
        policy = OperatingSettings.current()
        policy.preparation_mean_minutes = 20
        policy.save()
        response = self.client.post(self.url, {'action': 'confirm', 'token': review.context['token']})
        self.assertContains(response, 'El tiempo de preparación cambió')
        self.assertContains(response, '09:10')
        self.assertFalse(Reservation.objects.exists())
        response = self.client.post(self.url, {'action': 'confirm', 'token': review.context['token']})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reservation.objects.get().preparation_minutes, 20)

    def test_invalid_inputs_and_expired_tokens_cannot_save(self):
        for override in [dict(diagnosis=''), dict(patient_rut='12345678-0'), dict(desired_time='09:15'),
                         dict(duration_minutes=0), dict(fecha='9999-12-31'), dict(diagnosis='x' * 2001)]:
            with self.subTest(override=override):
                response = self.client.post(self.url, {**self.data, **override})
                self.assertTrue(response.context['form'].errors)
        self.client.post(self.url, {'action': 'confirm', 'token': 'no-existe'})
        result = self.search()
        token = result.context['token']
        self.client.post(self.url, {'action': 'confirm', 'token': token})  # No se seleccionó pabellón.
        session = self.client.session
        searches = session['reservation_searches']
        searches[token]['expires'] = 0
        session['reservation_searches'] = searches
        session.save()
        self.assertEqual(self.client.post(self.url, {'action': 'choose', 'token': token, 'room': self.other.pk}).status_code, 302)
        self.assertFalse(Reservation.objects.exists())

    def test_unavailable_room_hours_and_continuity_exclude_room(self):
        self.other.opening_time = time(10)
        self.other.save()
        self.assertNotIn(self.other, self.search().context['result']['rooms'])
        self.other.opening_time = time(7)
        self.other.save()
        self.reserve(clock=time(7), duration=60)
        self.assertNotIn(self.other, self.search().context['result']['rooms'])  # inicio 90 minutos después.

    def test_overnight_availability_checks_next_day(self):
        result = find_available_rooms(day=self.day, desired_time=time(23), duration_minutes=180)
        self.assertIn(self.other, result['rooms'])
        self.assertEqual(timezone.localtime(result['end']).time(), time(2))
        self.other.opening_time = time(0)
        self.other.save()
        self.reserve(clock=time(1), duration=60, day=self.day + timedelta(days=1))
        self.assertNotIn(self.other, find_available_rooms(day=self.day, desired_time=time(23), duration_minutes=180)['rooms'])

    def test_review_selection_is_not_changed_by_another_review(self):
        token = self.search().context['token']
        first = self.choose(token)
        second = self.choose(token, self.item.room)
        self.assertNotEqual(first.context['token'], second.context['token'])
        self.client.post(self.url, {'action': 'confirm', 'token': first.context['token']})
        self.assertEqual(Reservation.objects.get().room, self.other)

    def test_permissions(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        outsider = get_user_model().objects.create_user(username='sin-busqueda')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
