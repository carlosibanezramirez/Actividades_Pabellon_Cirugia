from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import get_connection
from django.test import TestCase
from django.utils import timezone

from .email_delivery import deliver_one, deliver_pending
from .models import Doctor, EmailNotification, EmailSettings, Reservation, Room
from .reminders import queue_reminders
from .tests import fixtures


class ReminderTests(TestCase):
    def setUp(self):
        self.operator, self.admin, self.item = fixtures()
        self.account = get_user_model().objects.create_user(username='reminder-doctor', email='doctor@example.test')
        self.doctor = self.item.doctor
        self.doctor.user = self.account
        self.doctor.save()
        self.config = EmailSettings(enabled=True, host='smtp.example.test', username='fake',
            from_email='notice@example.test', public_url='https://app.example.test')
        self.config.set_password('fake-test-only')
        self.config.save()
        self.now = timezone.now()
        self.planned = self.now + timedelta(hours=3)
        self.booking = Reservation.objects.create(room=self.item.room, doctor=self.doctor, procedure=self.item.procedure,
            starts_at=self.planned - timedelta(minutes=15), planned_start_at=self.planned,
            ends_at=self.planned + timedelta(hours=1), created_by=self.operator,
            patient_name='Paciente privado ficticio', patient_rut='12345678-5', diagnosis='Diagnóstico privado')

    def test_three_hour_boundary_one_email_only_to_doctor(self):
        self.assertEqual(self.config.reminder_minutes, 180)
        self.assertEqual(queue_reminders(self.now - timedelta(microseconds=1)), 0)
        self.assertEqual(queue_reminders(self.now), 1)
        self.assertEqual(queue_reminders(self.now + timedelta(minutes=1)), 0)
        notification = EmailNotification.objects.get()
        self.assertEqual(notification.recipient, self.account.email)
        self.assertEqual(notification.event, 'reminder')
        for private in [self.booking.patient_name, self.booking.patient_rut, self.booking.diagnosis]:
            self.assertNotIn(private, notification.body)
        self.assertIn('/avisos/reservas/', notification.body)

    def test_disabled_cancelled_pending_and_started_are_not_reminded(self):
        self.config.notify_reminder = False
        self.config.save()
        self.assertEqual(queue_reminders(self.now), 0)
        self.config.notify_reminder = True
        self.config.save()
        for field in ['cancelled_at', 'needs_rescheduling']:
            setattr(self.booking, field, self.now if field == 'cancelled_at' else True)
            self.booking.save()
            self.assertEqual(queue_reminders(self.now), 0)
            setattr(self.booking, field, None if field == 'cancelled_at' else False)
            self.booking.save()
        self.item.reservation = self.booking
        self.item.completed_at = self.now
        self.item.save()
        self.assertEqual(queue_reminders(self.now), 0)

    def test_reprogramming_skips_queued_reminder_and_generates_new_schedule(self):
        queue_reminders(self.now)
        old = EmailNotification.objects.get()
        self.booking.starts_at += timedelta(minutes=5)
        self.booking.planned_start_at += timedelta(minutes=5)
        self.booking.ends_at += timedelta(minutes=5)
        self.booking.save()
        with patch('theatre.email_delivery.smtp_connection') as smtp:
            self.assertTrue(deliver_one(self.now + timedelta(minutes=1)))
            smtp.assert_not_called()
        old.refresh_from_db()
        self.assertEqual(old.status, 'skipped')
        self.assertEqual(queue_reminders(self.now + timedelta(minutes=5)), 1)
        self.assertEqual(EmailNotification.objects.count(), 2)

    def test_cancellation_after_queuing_prevents_email(self):
        queue_reminders(self.now)
        self.booking.cancelled_at = self.now
        self.booking.save()
        with patch('theatre.email_delivery.smtp_connection') as smtp:
            deliver_pending()
            smtp.assert_not_called()
        self.assertEqual(EmailNotification.objects.get().status, 'skipped')

    def test_delivery_refreshes_room_and_sends_using_current_information(self):
        queue_reminders(self.now)
        self.booking.room = Room.objects.create(name='Pabellón destino del recordatorio')
        self.booking.save()
        backend = get_connection('django.core.mail.backends.locmem.EmailBackend')
        with patch('theatre.email_delivery.smtp_connection', return_value=backend):
            deliver_pending()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.booking.room.name, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, [self.account.email])

    def test_closer_bookings_notify_immediately_and_expired_do_not(self):
        self.booking.planned_start_at = self.now + timedelta(minutes=20)
        self.booking.starts_at = self.now + timedelta(minutes=5)
        self.booking.ends_at = self.now + timedelta(hours=1)
        self.booking.save()
        self.assertEqual(queue_reminders(self.now), 1)
        self.assertEqual(queue_reminders(self.now + timedelta(minutes=21)), 0)

    def test_configurable_time_and_doctor_email_precedence(self):
        self.config.reminder_minutes = 120
        self.config.save()
        self.doctor.email = 'catalog-doctor@example.test'
        self.doctor.save()
        self.assertEqual(queue_reminders(self.now), 0)
        self.assertEqual(queue_reminders(self.now + timedelta(hours=1)), 1)
        self.assertEqual(EmailNotification.objects.get().recipient, self.doctor.email)

    def test_clinical_start_after_queue_omits_reminder(self):
        from .models import Event
        queue_reminders(self.now)
        self.item.reservation = self.booking
        self.item.save()
        Event.objects.create(intervention=self.item, stage=3, occurred_at=self.now, original_at=self.now, recorded_by=self.operator)
        with patch('theatre.email_delivery.smtp_connection') as smtp:
            deliver_pending()
            smtp.assert_not_called()
        self.assertEqual(EmailNotification.objects.get().status, 'skipped')

    def test_changed_contact_skips_old_address_and_queues_new_address(self):
        queue_reminders(self.now)
        self.doctor.email = 'new-doctor@example.test'
        self.doctor.save()
        with patch('theatre.email_delivery.smtp_connection') as smtp:
            deliver_pending()
            smtp.assert_not_called()
        self.assertEqual(EmailNotification.objects.get().status, 'skipped')
        self.assertEqual(queue_reminders(self.now), 1)
        self.assertEqual(EmailNotification.objects.get(status='pending').recipient, 'new-doctor@example.test')
