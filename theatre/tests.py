from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Correction, Doctor, Event, Intervention, Procedure, Room
from .services import correct_event, create_intervention, record_event


def fixtures():
    call_command('setup_roles', verbosity=0)
    user = get_user_model().objects.create_user(username='operador', password='test-only-password')
    user.groups.add(Group.objects.get(name='Operador'))
    administrator = get_user_model().objects.create_user(username='administrador', password='test-only-password', is_staff=True)
    administrator.groups.add(Group.objects.get(name='Administrador'))
    room = Room.objects.create(name='Pabellón de prueba')
    procedure = Procedure.objects.create(name='Operación ficticia')
    doctor = Doctor.objects.create(name='Profesional de prueba')
    intervention = create_intervention(user=user, room=room, procedure=procedure, doctor=doctor)
    return user, administrator, intervention


class WorkflowTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()
        self.client.force_login(self.user)

    def record(self, stage, at=None):
        if at:
            with patch('theatre.services.timezone.now', return_value=at):
                return record_event(user=self.user, intervention_id=self.intervention.pk, stage=stage)
        return record_event(user=self.user, intervention_id=self.intervention.pk, stage=stage)

    def test_full_sequence_completion_persistence_and_room_reuse(self):
        start = timezone.now()
        for stage in range(1, 10):
            event = self.record(stage, start + timedelta(minutes=stage))
            self.assertEqual(event.original_at, event.occurred_at)
            self.assertEqual(event.recorded_by, self.user)
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.completed_at, event.occurred_at)
        self.client.logout()
        self.client.force_login(self.user)
        response = self.client.get(reverse('detail', args=[self.intervention.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '9 de 9')
        self.assertContains(response, '0:08:00')
        self.assertNotContains(response, 'action="' + reverse('record', args=[self.intervention.pk, 9]) + '"')
        other = create_intervention(user=self.user, room=self.intervention.room, procedure=self.intervention.procedure, doctor=self.intervention.doctor)
        self.assertNotEqual(other.pk, self.intervention.pk)

    def test_skipped_duplicate_and_after_completion_rejected(self):
        with self.assertRaises(ValidationError):
            self.record(2)
        self.record(1)
        with self.assertRaises(ValidationError):
            self.record(1)
        for stage in range(2, 10):
            self.record(stage)
        with self.assertRaises(ValidationError):
            self.record(10)
        self.assertEqual(self.intervention.events.count(), 9)

    def test_only_next_button_enabled_and_tampered_request_rejected(self):
        response = self.client.get(reverse('detail', args=[self.intervention.pk]))
        self.assertContains(response, 'action="' + reverse('record', args=[self.intervention.pk, 1]) + '"')
        self.assertContains(response, '<button disabled', count=8)
        response = self.client.post(reverse('record', args=[self.intervention.pk, 4]), follow=True)
        self.assertContains(response, 'no corresponde al siguiente paso')
        self.assertEqual(self.intervention.events.count(), 0)
        self.assertEqual(self.client.get(reverse('record', args=[self.intervention.pk, 1])).status_code, 405)

    def test_unauthenticated_and_unassigned_users_denied(self):
        anonymous = Client()
        self.assertEqual(anonymous.get('/').status_code, 302)
        user = get_user_model().objects.create_user(username='sin-perfil', password='test-only-password')
        anonymous.force_login(user)
        self.assertEqual(anonymous.get('/').status_code, 403)
        self.assertEqual(anonymous.post(reverse('record', args=[self.intervention.pk, 1])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            record_event(user=user, intervention_id=self.intervention.pk, stage=1)

    def test_password_authentication_and_post_logout(self):
        client = Client()
        self.assertFalse(client.login(username='operador', password='incorrecta'))
        self.assertTrue(client.login(username='operador', password='test-only-password'))
        self.assertEqual(client.get(reverse('logout')).status_code, 405)
        self.assertEqual(client.post(reverse('logout')).status_code, 302)
        self.assertEqual(client.get('/').status_code, 302)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('record', args=[self.intervention.pk, 1])).status_code, 403)
        self.assertEqual(self.intervention.events.count(), 0)

    def test_room_occupancy_and_inactive_catalog(self):
        with self.assertRaises(ValidationError):
            create_intervention(user=self.user, room=self.intervention.room, procedure=self.intervention.procedure, doctor=self.intervention.doctor)
        room = Room.objects.create(name='Inactivo', active=False)
        with self.assertRaises(ValidationError):
            create_intervention(user=self.user, room=room, procedure=self.intervention.procedure, doctor=self.intervention.doctor)
        response = self.client.get(reverse('create'))
        self.assertNotContains(response, '>Inactivo</option>')

    def test_create_page_submission_and_validation(self):
        room = Room.objects.create(name='Segundo pabellón')
        response = self.client.post(reverse('create'), {'room': room.pk, 'procedure': self.intervention.procedure_id, 'doctor': self.intervention.doctor_id})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Intervention.objects.count(), 2)
        response = self.client.post(reverse('create'), {'room': room.pk, 'procedure': self.intervention.procedure_id, 'doctor': self.intervention.doctor_id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ya tiene una intervención en curso')

    def test_future_clock_regression_rejected(self):
        self.record(1)
        with patch('theatre.services.timezone.now', return_value=self.intervention.created_at - timedelta(seconds=10)):
            with self.assertRaises(ValidationError):
                self.record(2)

    def test_correction_authorization_and_audit(self):
        first = self.record(1)
        self.record(2)
        url = reverse('correct', args=[self.intervention.pk, first.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        new_at = self.intervention.created_at + (first.occurred_at - self.intervention.created_at) / 2
        with self.assertRaises(PermissionDenied):
            correct_event(user=self.user, intervention_id=self.intervention.pk, event_id=first.pk, new_at=new_at, reason='Ajuste', expected_at=first.occurred_at)
        original = first.occurred_at
        correct_event(user=self.administrator, intervention_id=self.intervention.pk, event_id=first.pk, new_at=new_at, reason='Corrección de prueba', expected_at=original)
        first.refresh_from_db()
        audit = Correction.objects.get(event=first)
        self.assertEqual(first.original_at, original)
        self.assertEqual(first.occurred_at, new_at)
        self.assertEqual(audit.previous_at, original)
        self.assertEqual(audit.new_at, new_at)
        self.assertEqual(audit.corrected_by, self.administrator)
        self.assertContains(self.client.get(reverse('detail', args=[self.intervention.pk])), 'Corrección de prueba')
        with self.assertRaises(ValidationError):
            correct_event(user=self.administrator, intervention_id=self.intervention.pk, event_id=first.pk, new_at=new_at, reason='Obsoleto', expected_at=original)
        self.assertEqual(Correction.objects.count(), 1)

    def test_invalid_corrections_leave_no_audit(self):
        first = self.record(1)
        second = self.record(2)
        cases = [
            (first, first.occurred_at, ''),
            (first, second.occurred_at + timedelta(seconds=1), 'Fuera de orden'),
            (second, first.occurred_at - timedelta(seconds=1), 'Fuera de orden'),
            (first, self.intervention.created_at - timedelta(seconds=1), 'Anterior'),
            (first, timezone.now() + timedelta(hours=1), 'Futuro'),
            (first, first.occurred_at, 'Sin cambio'),
        ]
        for event, value, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(ValidationError):
                correct_event(user=self.administrator, intervention_id=self.intervention.pk, event_id=event.pk, new_at=value, reason=reason, expected_at=event.occurred_at)
        self.assertEqual(Correction.objects.count(), 0)

    def test_correction_page_and_form_with_timezone(self):
        event = self.record(1)
        self.client.force_login(self.administrator)
        url = reverse('correct', args=[self.intervention.pk, event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'expected_at')
        new_at = self.intervention.created_at + (event.occurred_at - self.intervention.created_at) / 2
        response = self.client.post(url, {'new_at': new_at.isoformat(), 'expected_at': event.occurred_at.isoformat(), 'reason': 'Prueba de formulario'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Correction.objects.count(), 1)

    def test_final_correction_updates_completion(self):
        for stage in range(1, 10):
            self.record(stage)
        event = self.intervention.events.get(stage=9)
        previous = self.intervention.events.get(stage=8)
        correct_event(user=self.administrator, intervention_id=self.intervention.pk, event_id=event.pk, new_at=previous.occurred_at, reason='Prueba de cierre', expected_at=event.occurred_at)
        self.intervention.refresh_from_db()
        self.assertEqual(self.intervention.completed_at, previous.occurred_at)

    def test_admin_cannot_edit_or_delete_audit_records(self):
        superuser = get_user_model().objects.create_superuser(username='super', password='test-only-password')
        self.client.force_login(superuser)
        event = self.record(1)
        response = self.client.post(reverse('admin:theatre_event_change', args=[event.pk]), {'stage': 9})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse('admin:theatre_event_delete', args=[event.pk]))
        self.assertEqual(response.status_code, 403)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo de filas real en PostgreSQL')
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()

    def run_parallel(self, operation):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                operation(user)
                return 'ok'
            except ValidationError:
                return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ['ok', 'rejected'])

    def test_simultaneous_click_records_once(self):
        self.run_parallel(lambda user: record_event(user=user, intervention_id=self.intervention.pk, stage=1))
        self.assertEqual(Event.objects.count(), 1)

    def test_simultaneous_room_assignment_creates_once(self):
        room = Room.objects.create(name='Pabellón concurrente')
        self.run_parallel(lambda user: create_intervention(user=user, room=room, procedure=self.intervention.procedure, doctor=self.intervention.doctor))
        self.assertEqual(Intervention.objects.filter(room=room).count(), 1)
