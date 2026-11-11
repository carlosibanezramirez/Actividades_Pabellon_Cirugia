from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Event, PreoperativeActivity
from .services import complete_preoperative_activity, record_event, correct_event
from .tests import fixtures


class PreoperativeTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.client.force_login(self.user)

    def complete(self, kind):
        return complete_preoperative_activity(user=self.user, intervention_id=self.item.pk, kind=kind)

    def event(self, stage):
        return record_event(user=self.user, intervention_id=self.item.pk, stage=stage)

    def test_can_complete_before_or_during_room_preparation_in_any_order(self):
        before = timezone.now()
        operation = self.complete('operation')
        self.assertGreaterEqual(operation.completed_at, before)
        self.assertEqual(operation.completed_by, self.user)
        self.assertEqual(self.item.events.count(), 0)
        self.event(1)
        anesthesia = self.complete('anesthesia')
        self.assertGreaterEqual(anesthesia.completed_at, operation.completed_at)
        self.event(2)
        self.event(3)
        self.assertEqual(self.item.preoperative_activities.count(), 2)
        self.assertEqual(self.item.events.count(), 3)

    def test_either_consent_can_be_first_and_prep_can_finish_before_both(self):
        self.complete('anesthesia')
        self.event(1)
        self.event(2)
        with self.assertRaisesMessage(ValidationError, 'ambos consentimientos'):
            self.event(3)
        self.complete('operation')
        self.event(3)

    def test_missing_consent_blocks_service_and_post_and_disables_button(self):
        self.event(1)
        self.event(2)
        self.assertEqual(self.item.preoperative_activities.count(), 0)
        with self.assertRaises(ValidationError):
            self.event(3)
        response = self.client.post(reverse('record', args=[self.item.pk, 3]), follow=True)
        self.assertContains(response, 'Complete ambos consentimientos')
        self.assertNotContains(response, f'action="{reverse("record", args=[self.item.pk, 3])}"')
        self.complete('operation')
        self.assertNotContains(self.client.get(reverse('detail', args=[self.item.pk])),
                              f'action="{reverse("record", args=[self.item.pk, 3])}"')
        self.complete('anesthesia')
        self.assertContains(self.client.get(reverse('detail', args=[self.item.pk])),
                            f'action="{reverse("record", args=[self.item.pk, 3])}"')

    def test_duplicate_invalid_and_late_marks_rejected(self):
        self.complete('operation')
        with self.assertRaises(ValidationError):
            self.complete('operation')
        with self.assertRaises(ValidationError):
            self.complete('invalid')
        self.item.completed_at = timezone.now()
        self.item.save()
        with self.assertRaises(ValidationError):
            self.complete('anesthesia')

    def test_historical_advanced_intervention_not_backfilled_or_modified(self):
        for stage in [1, 2, 3]:
            at = timezone.now()
            Event.objects.create(intervention=self.item, stage=stage, occurred_at=at, original_at=at, recorded_by=self.user)
        with self.assertRaises(ValidationError):
            self.complete('operation')
        self.assertEqual(self.item.preoperative_activities.count(), 0)
        self.event(4)  # La actividad en curso se puede continuar.
        response = self.client.get(reverse('activity_history', args=[self.item.pk]))
        self.assertContains(response, 'Sin registro')
        self.assertNotContains(response, 'Marcar como completada')

    def test_completed_cards_hide_but_counts_and_history_remain(self):
        self.complete('operation')
        response = self.client.get(reverse('detail', args=[self.item.pk]))
        self.assertNotContains(response, '<h2>Firma Consentimiento Informado Operación</h2>')
        self.assertContains(response, '<h2>Firma Consentimiento Informado Anestesia</h2>')
        self.assertContains(response, '<strong>1 de 2</strong><span>Eventos pre-operatorios</span>')
        self.assertContains(response, '<strong>0 de 9</strong><span>Eventos cirugía</span>')
        self.assertNotContains(response, 'Marca cada consentimiento al completarse.')
        self.event(1)
        response = self.client.get(reverse('detail', args=[self.item.pk]))
        self.assertNotContains(response, '<h2>Inicio de preparación del pabellón</h2>')
        self.assertContains(response, f'action="{reverse("record", args=[self.item.pk, 2])}"')
        history = self.client.get(reverse('activity_history', args=[self.item.pk]))
        self.assertContains(history, 'Firma Consentimiento Informado Operación')
        self.assertContains(history, 'Inicio de preparación del pabellón')
        self.assertNotContains(history, 'Marcar como completada')

    def test_correction_cannot_place_anesthesia_before_consent_completion(self):
        self.event(1)
        second = self.event(2)
        self.complete('operation')
        self.complete('anesthesia')
        third = self.event(3)
        with self.assertRaisesMessage(ValidationError, 'anterior al registro de los consentimientos'):
            correct_event(user=self.admin, intervention_id=self.item.pk, event_id=third.pk,
                          new_at=second.occurred_at, expected_at=third.occurred_at, reason='Corrección ficticia')

    def test_endpoint_permission_post_only_and_persisted_timestamp(self):
        url = reverse('complete_preoperative', args=[self.item.pk, 'operation'])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse('detail', args=[self.item.pk]) + '#pending-activities')
        activity = PreoperativeActivity.objects.get()
        response = self.client.get(reverse('activity_history', args=[self.item.pk]))
        self.assertContains(response, 'Firma Consentimiento Informado Operación')
        self.assertContains(response, timezone.localtime(activity.completed_at).strftime('%d/%m/%Y %H:%M:%S'))
        outsider = get_user_model().objects.create_user(username='sin-preoperatorio')
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url).status_code, 403)
        with self.assertRaises(PermissionDenied):
            complete_preoperative_activity(user=outsider, intervention_id=self.item.pk, kind='anesthesia')


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo real de PostgreSQL')
class PreoperativeConcurrencyTests(TransactionTestCase):
    def test_duplicate_submissions_store_only_one_completion(self):
        user, _, item = fixtures()
        barrier = Barrier(2)

        def complete(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                try:
                    complete_preoperative_activity(user=actor, intervention_id=item.pk, kind='operation')
                    return 'saved'
                except ValidationError:
                    return 'duplicate'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(complete, range(2))), ['saved', 'duplicate'])
        self.assertEqual(PreoperativeActivity.objects.count(), 1)
