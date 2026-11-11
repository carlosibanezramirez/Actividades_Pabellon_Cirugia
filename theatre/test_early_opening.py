from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .dashboard import room_snapshot
from .models import Reservation
from .scheduling import occupancy
from .services import create_intervention, record_event, complete_preoperative_activity
from .tests import fixtures


class EarlyOpeningTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.start = timezone.now() + timedelta(days=2)
        self.booking = Reservation.objects.create(room=self.item.room, doctor=self.item.doctor,
            procedure=self.item.procedure, patient_name='Paciente ficticio anticipado', patient_rut='12345678-5',
            starts_at=self.start, planned_start_at=self.start + timedelta(minutes=15),
            ends_at=self.start + timedelta(hours=2), created_by=self.user)

    def open(self, booking=None):
        return create_intervention(user=self.user, room=self.item.room, doctor=self.item.doctor,
            procedure=self.item.procedure, anesthetist=self.item.anesthetist, reservation=booking or self.booking)

    def test_opening_long_before_preparation_allows_consents_without_occupying_room(self):
        early = self.open()  # El pabellón todavía tiene otra intervención física abierta.
        self.assertFalse(early.room_engaged)
        for kind in ['operation', 'anesthesia']:
            complete_preoperative_activity(user=self.user, intervention_id=early.pk, kind=kind)
        with self.assertRaises(ValidationError):
            record_event(user=self.user, intervention_id=early.pk, stage=1)
        self.assertFalse(any(p['intervention'] and p['intervention'].pk == early.pk
                             for p in occupancy(timezone.localdate())[1]))
        rows, _ = room_snapshot()
        self.assertEqual(next(r for r in rows if r['room'] == self.item.room)['intervention'].pk, self.item.pk)
        second = Reservation.objects.create(room=self.item.room, doctor=self.item.doctor,
            procedure=self.item.procedure, patient_name='Otro paciente ficticio', starts_at=self.start + timedelta(days=1),
            ends_at=self.start + timedelta(days=1, hours=2), created_by=self.user)
        self.assertFalse(self.open(second).room_engaged)

    def test_exact_thirty_minute_boundary_and_events_can_advance_after_preparation(self):
        early = self.open()
        self.item.completed_at = timezone.now()
        self.item.save()
        for kind in ['operation', 'anesthesia']:
            complete_preoperative_activity(user=self.user, intervention_id=early.pk, kind=kind)
        limit = self.start - timedelta(minutes=30)
        with patch('theatre.services.timezone.now', return_value=limit - timedelta(microseconds=1)):
            with self.assertRaises(ValidationError):
                record_event(user=self.user, intervention_id=early.pk, stage=1)
        with patch('theatre.services.timezone.now', return_value=limit):
            record_event(user=self.user, intervention_id=early.pk, stage=1)
            record_event(user=self.user, intervention_id=early.pk, stage=2)
            record_event(user=self.user, intervention_id=early.pk, stage=3)
        early.refresh_from_db()
        self.assertTrue(early.room_engaged)
        self.assertEqual(early.events.count(), 3)

    def test_early_preparation_cannot_interrupt_another_reservation_or_active_intervention(self):
        early = self.open()
        limit = self.start - timedelta(minutes=30)
        with patch('theatre.services.timezone.now', return_value=limit):
            with self.assertRaisesMessage(ValidationError, 'intervención en curso'):
                record_event(user=self.user, intervention_id=early.pk, stage=1)
        self.item.completed_at = timezone.now()
        self.item.save()
        Reservation.objects.create(room=self.item.room, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Reserva anterior ficticia', starts_at=self.start - timedelta(hours=2),
            ends_at=self.start - timedelta(minutes=5), created_by=self.user)
        with patch('theatre.services.timezone.now', return_value=limit):
            with self.assertRaisesMessage(ValidationError, 'coincide con otra reserva'):
                record_event(user=self.user, intervention_id=early.pk, stage=1)
        early.refresh_from_db()
        self.assertFalse(early.room_engaged)

    def test_future_open_form_enables_preoperative_and_disables_room_preparation(self):
        self.client.force_login(self.user)
        url = reverse('open_reservation', args=[self.booking.pk])
        self.assertContains(self.client.get(url), 'Abrir preoperatorio y eventos')
        response = self.client.post(url, {'anesthetist': self.item.anesthetist_id}, follow=True)
        self.assertContains(response, 'Marcar como completada')
        self.assertContains(response, '30 minutos antes de la preparación programada')
        self.assertNotContains(response, 'Podrá comenzar el registro desde')
