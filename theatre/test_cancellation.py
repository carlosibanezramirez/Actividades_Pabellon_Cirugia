from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .forms import CancelReservationForm
from .models import CancellationReason, Reservation
from .occupancy_summary import active_reservations_for_day
from .scheduling import occupancy
from .services import create_intervention
from .tests import fixtures
from .weekly_scheduling import cancel_reservation, continuous_day, reserve_continuous, reservation_revision, reschedule_reservation


class CancellationTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.day = timezone.localdate() + timedelta(days=7)
        self.reason = CancellationReason.objects.create(name='Solicitud del paciente')
        self.booking = reserve_continuous(user=self.user, room=self.item.room, day=self.day,
            desired_time=time(9, 30), duration_minutes=90, doctor=self.item.doctor,
            procedure=self.item.procedure, patient_name='Paciente ficticio cancelación', patient_rut='12345678-5')
        self.client.force_login(self.user)

    def cancel(self, **overrides):
        args = dict(user=self.user, reservation_id=self.booking.pk, reason=self.reason,
                    expected_revision=reservation_revision(self.booking))
        args.update(overrides)
        return cancel_reservation(**args)

    def test_cancel_records_audit_and_frees_interval_and_counter(self):
        cancelled = self.cancel()
        self.assertIsNotNone(cancelled.cancelled_at)
        self.assertEqual(cancelled.cancelled_by, self.user)
        self.assertEqual(cancelled.cancellation_reason, self.reason)
        self.assertEqual(cancelled.cancellation_reason_name, self.reason.name)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(active_reservations_for_day(self.item.room, self.day), [])
        self.assertEqual(continuous_day(self.item.room, self.day)['booking_blocks'], [])
        self.assertFalse(any(p['reservation'] for p in occupancy(self.day)[1]))
        replacement = reserve_continuous(user=self.user, room=self.item.room, day=self.day,
            desired_time=time(9, 30), duration_minutes=90, doctor=self.item.doctor,
            procedure=self.item.procedure, patient_name='Paciente ficticio reemplazo', patient_rut='12345678-5')
        self.assertNotEqual(replacement.pk, self.booking.pk)
        self.reason.name = 'Causa renombrada'
        self.reason.save()
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.cancellation_reason_name, 'Solicitud del paciente')
        with self.assertRaises(ProtectedError):
            self.reason.delete()
        detail = self.client.get(reverse('reservation_detail', args=[cancelled.pk]))
        self.assertContains(detail, 'Solicitud del paciente')
        self.assertContains(detail, 'Cancelada el')

    def test_inactive_reason_and_missing_reason_are_rejected(self):
        self.reason.active = False
        self.reason.save()
        self.assertFalse(CancelReservationForm(data={'reason': self.reason.pk, 'revision': 'x'}).is_valid())
        with self.assertRaises(ValidationError):
            self.cancel()
        self.assertFalse(CancelReservationForm(data={'revision': 'x'}).is_valid())
        self.booking.refresh_from_db()
        self.assertIsNone(self.booking.cancelled_at)

    def test_started_or_expired_reservations_cannot_be_cancelled(self):
        self.item.reservation = self.booking
        self.item.save()
        with self.assertRaises(ValidationError):
            self.cancel()
        self.item.reservation = None
        self.item.save()
        Reservation.objects.filter(pk=self.booking.pk).update(
            starts_at=timezone.now() - timedelta(hours=2), planned_start_at=timezone.now() - timedelta(minutes=105),
            ends_at=timezone.now() - timedelta(minutes=15))
        self.booking.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.cancel()

    def test_stale_and_repeated_cancellation_and_reschedule_are_rejected(self):
        revision = reservation_revision(self.booking)
        cancelled = self.cancel()
        with self.assertRaises(ValidationError):
            self.cancel(expected_revision=revision)
        with self.assertRaises(ValidationError):
            self.cancel(expected_revision=reservation_revision(cancelled))
        with self.assertRaises(ValidationError):
            reschedule_reservation(user=self.user, reservation_id=cancelled.pk, room=self.item.room,
                day=self.day + timedelta(days=1), desired_time=time(12), expected_revision=reservation_revision(cancelled))
        self.item.completed_at = timezone.now()
        self.item.save()
        with self.assertRaisesMessage(ValidationError, 'cancelada'):
            create_intervention(user=self.user, room=self.item.room, procedure=self.item.procedure,
                doctor=self.item.doctor, anesthetist=self.item.anesthetist, reservation=cancelled)

    def test_cancelled_booking_does_not_constrain_later_start_gap(self):
        self.cancel()
        reserve_continuous(user=self.user, room=self.item.room, day=self.day, desired_time=time(17),
            duration_minutes=90, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio tarde', patient_rut='12345678-5')

    def test_endpoint_and_admin_reason_permissions(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('admin:theatre_cancellationreason_add')).status_code, 200)
        self.client.force_login(self.user)
        edit = self.client.get(reverse('reservation_edit', args=[self.booking.pk]))
        revision = edit.context['cancel_form'].initial['revision']
        url = reverse('reservation_cancel', args=[self.booking.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'cancellation-revision': revision}).status_code, 422)
        data = {'cancellation-revision': revision, 'cancellation-reason': self.reason.pk}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(self.client.post(url, data).status_code, 422)
        self.assertContains(self.client.get(reverse('reservation_edit', args=[self.booking.pk])), 'Reserva cancelada')
        outsider = get_user_model().objects.create_user(username='sin-permiso-cancelar')
        with self.assertRaises(PermissionDenied):
            self.cancel(user=outsider)
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url, data).status_code, 403)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo real de PostgreSQL')
class CancellationConcurrencyTests(TransactionTestCase):
    def test_cancel_and_move_cannot_both_overwrite_same_revision(self):
        user, _, item = fixtures()
        day = timezone.localdate() + timedelta(days=7)
        reason = CancellationReason.objects.create(name='Solicitud del paciente')
        booking = reserve_continuous(user=user, room=item.room, day=day, desired_time=time(9),
            duration_minutes=90, doctor=item.doctor, procedure=item.procedure,
            patient_name='Paciente ficticio simultáneo', patient_rut='12345678-5')
        revision = reservation_revision(booking)
        barrier = Barrier(2)

        def change(action):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                try:
                    if action == 'cancel':
                        cancel_reservation(user=actor, reservation_id=booking.pk, reason=reason, expected_revision=revision)
                    else:
                        reschedule_reservation(user=actor, reservation_id=booking.pk, room=item.room,
                            day=day + timedelta(days=1), desired_time=time(10), expected_revision=revision)
                    return 'saved'
                except ValidationError:
                    return 'stale'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(change, ['cancel', 'move']))
        self.assertCountEqual(results, ['saved', 'stale'])
