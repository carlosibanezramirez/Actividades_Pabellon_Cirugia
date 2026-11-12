import smtplib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.core import mail
from django.core.mail import get_connection
from django.db import transaction, connection, close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .email_delivery import deliver_one, deliver_pending
from .forms import EmailSettingsForm
from .models import CancellationReason, EmailNotification, EmailSettings, Room
from .notifications import queue_reservation_notification
from .overruns import relocate_next_reservation
from .reservation_adjustments import save_adjustment
from .tests import fixtures
from .weekly_scheduling import reserve_continuous, reschedule_reservation, cancel_reservation, reservation_revision


class NotificationTests(TestCase):
    def setUp(self):
        self.user, self.admin, self.item = fixtures()
        self.user.email = 'operator@example.test'
        self.user.save()
        self.admin.email = 'admin@example.test'
        self.admin.save()
        self.item.doctor.email = 'doctor@example.test'
        self.item.doctor.save()
        self.config = EmailSettings(host='smtp.example.test', username='smtp-user', from_email='notice@example.test',
                                    public_url='https://app.example.test', enabled=True)
        self.config.set_password('fictional-smtp-password')
        self.config.save()
        self.day = timezone.localdate() + timedelta(days=7)

    def booking(self, **overrides):
        data = dict(user=self.user, room=self.item.room, day=self.day, desired_time=time(9, 30),
                    duration_minutes=90, doctor=self.item.doctor, procedure=self.item.procedure,
                    patient_name='Paciente confidencial ficticio', patient_rut='12345678-5', diagnosis='Diagnóstico confidencial ficticio')
        data.update(overrides)
        return reserve_continuous(**data)

    def config_data(self, **overrides):
        data = dict(host='smtp.example.test', port=587, connection_type='auto', username='smtp-user', enabled='on',
                    from_email='notice@example.test', from_name='Surgeon', public_url='https://app.example.test',
                    notify_reminder='on', reminder_minutes=180, notify_confirmed='on', notify_modified='on', notify_cancelled='on', notify_relocated='on', notify_reschedule='on')
        data.update(overrides)
        return data

    def test_credentials_encrypted_and_blank_edit_keeps_password(self):
        self.assertNotIn('fictional-smtp-password', self.config.password_ciphertext)
        self.assertEqual(self.config.get_password(), 'fictional-smtp-password')
        form = EmailSettingsForm(data=self.config_data(smtp_password=''), instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(EmailSettings.objects.get().get_password(), 'fictional-smtp-password')
        self.assertNotIn('fictional-smtp-password', form.as_p())
        changed = EmailSettingsForm(data=self.config_data(smtp_password='replacement-test-only'), instance=self.config)
        self.assertTrue(changed.is_valid(), changed.errors)
        changed.save()
        self.assertEqual(EmailSettings.objects.get().get_password(), 'replacement-test-only')
        with override_settings(SMTP_CREDENTIAL_KEY='different-test-key'):
            with self.assertRaises(Exception):
                EmailSettings.objects.get().get_password()

    def test_enabling_requires_credentials_and_users_doctors_have_email_fields(self):
        empty = EmailSettingsForm(data=self.config_data(), instance=EmailSettings())
        self.assertFalse(empty.is_valid())
        self.assertIn('enabled', empty.errors)
        from .forms import ProfileUserCreationForm, ProfileUserChangeForm
        self.assertIn('email', ProfileUserCreationForm().fields)
        self.assertIn('email', ProfileUserChangeForm(instance=self.user).fields)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin:theatre_doctor_change', args=[self.item.doctor_id])), 'name="email"')

    def test_confirmation_recipients_deduplicated_and_no_patient_data_in_message(self):
        self.admin.email = 'DOCTOR@example.test'
        self.admin.save()
        booking = self.booking()
        self.assertCountEqual(EmailNotification.objects.values_list('recipient', flat=True),
                              ['doctor@example.test', 'operator@example.test'])
        for notification in EmailNotification.objects.all():
            self.assertNotIn(booking.patient_name, notification.body)
            self.assertNotIn(booking.patient_rut, notification.body)
            self.assertNotIn(booking.diagnosis, notification.body)
            self.assertNotIn(booking.procedure.name, notification.body)
            self.assertIn('https://app.example.test/avisos/reservas/', notification.body)
        queue_reservation_notification(booking, 'confirmed', event_key=f'created:{booking.pk}')
        self.assertEqual(EmailNotification.objects.count(), 2)

    def test_manual_change_and_cancellation_queue_supported_events(self):
        booking = self.booking()
        moved = reschedule_reservation(user=self.user, reservation_id=booking.pk, room=self.item.room,
            day=self.day + timedelta(days=1), desired_time=time(11), expected_revision=reservation_revision(booking))
        reason = CancellationReason.objects.create(name='Solicitud ficticia')
        cancel_reservation(user=self.user, reservation_id=moved.pk, reason=reason, expected_revision=reservation_revision(moved))
        for event in ['confirmed', 'modified', 'cancelled']:
            self.assertEqual(EmailNotification.objects.filter(event=event).count(), 3)
        self.assertIn('Horario/pabellón anterior', EmailNotification.objects.filter(event='modified').first().body)

    def test_disabled_events_no_queue_and_rollback_rolls_back_outbox(self):
        self.config.notify_confirmed = False
        self.config.save()
        booking = self.booking()
        self.assertEqual(EmailNotification.objects.count(), 0)
        self.config.enabled = False
        self.config.save()
        queue_reservation_notification(booking, 'cancelled')
        self.assertEqual(EmailNotification.objects.count(), 0)
        self.config.enabled = True
        self.config.notify_confirmed = True
        self.config.save()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.booking(day=self.day + timedelta(days=1))
                raise RuntimeError('rollback')
        self.assertEqual(EmailNotification.objects.count(), 0)

    def test_pending_reschedule_queues_its_own_notice(self):
        booking = self.booking()
        save_adjustment(booking, self.item, self.user, booking.ends_at, booking.ends_at, booking.ends_at,
                        'Atraso ficticio', needs_rescheduling=True)
        self.assertEqual(EmailNotification.objects.filter(event='reschedule').count(), 3)
        self.assertIn('sin tiempo útil', EmailNotification.objects.filter(event='reschedule').first().body)

    def test_relocation_queues_room_change_notice(self):
        from .models import Event
        booking = self.booking()
        following = self.booking(desired_time=time(11, 30), duration_minutes=90)
        self.item.reservation = booking
        self.item.save()
        at = booking.ends_at - timedelta(minutes=20)
        Event.objects.create(intervention=self.item, stage=6, occurred_at=at, original_at=at, recorded_by=self.user)
        target = Room.objects.create(name='Destino ficticio correo')
        relocation = relocate_next_reservation(self.item.pk, booking.ends_at + timedelta(minutes=10))
        self.assertEqual(relocation.to_room, target)
        self.assertEqual(EmailNotification.objects.filter(event='relocated').count(), 3)
        self.assertIn(target.name, EmailNotification.objects.filter(event='relocated').first().body)
        self.assertEqual(EmailNotification.objects.filter(reservation=following, event='relocated').count(), 3)

    def test_successful_delivery_uses_single_recipient_and_no_repeat(self):
        self.booking()
        backend = get_connection('django.core.mail.backends.locmem.EmailBackend')
        with patch('theatre.email_delivery.smtp_connection', return_value=backend):
            self.assertEqual(deliver_pending(), 3)
            self.assertEqual(deliver_pending(), 0)
        self.assertEqual(EmailNotification.objects.filter(status='sent').count(), 3)
        self.assertEqual(len(mail.outbox), 3)
        self.assertTrue(all(len(message.to) == 1 for message in mail.outbox))
        self.assertTrue(all('Message-ID' in message.extra_headers for message in mail.outbox))

    def test_smtp_transport_parameters_starttls_auth_and_timeout(self):
        from .email_delivery import smtp_connection
        with patch('theatre.email_delivery.get_connection') as get:
            smtp_connection(self.config)
        self.assertEqual(get.call_args.kwargs['port'], 587)
        self.assertTrue(get.call_args.kwargs['use_tls'])
        self.assertFalse(get.call_args.kwargs['use_ssl'])
        self.assertEqual(get.call_args.kwargs['password'], 'fictional-smtp-password')
        self.assertEqual(get.call_args.kwargs['timeout'], 15)

    def test_connection_modes_follow_port_or_explicit_selection(self):
        from .email_delivery import smtp_connection
        for port, mode, tls, ssl in [(587, 'auto', True, False), (465, 'auto', False, True),
                                     (25, 'auto', False, False), (2525, 'starttls', True, False),
                                     (587, 'plain', False, False), (2525, 'tls', False, True)]:
            with self.subTest(port=port, mode=mode):
                self.config.port, self.config.connection_type = port, mode
                with patch('theatre.email_delivery.get_connection') as connection:
                    smtp_connection(self.config)
                self.assertEqual(connection.call_args.kwargs['use_tls'], tls)
                self.assertEqual(connection.call_args.kwargs['use_ssl'], ssl)
        form = EmailSettingsForm(data=self.config_data(port=2525, connection_type='auto'), instance=self.config)
        self.assertFalse(form.is_valid())
        self.assertIn('connection_type', form.errors)

    def test_failure_retries_then_marks_failed_without_logging_credentials(self):
        self.booking()
        notification = EmailNotification.objects.order_by('pk').first()
        EmailNotification.objects.exclude(pk=notification.pk).delete()
        error = smtplib.SMTPAuthenticationError(535, b'fictional-smtp-password smtp-user')
        with patch('theatre.email_delivery.smtp_connection', side_effect=error):
            for attempt in range(1, 6):
                self.assertTrue(deliver_one(now=notification.next_attempt_at))
                notification.refresh_from_db()
                self.assertEqual(notification.attempts, attempt)
                self.assertNotIn('fictional-smtp-password', notification.last_error)
        self.assertEqual(notification.status, 'failed')
        self.assertFalse(deliver_one())
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin:theatre_emailnotification_changelist'),
            {'action': 'retry_failed', '_selected_action': [notification.pk]})
        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertEqual(notification.status, 'pending')
        self.assertEqual(notification.attempts, 0)

    def test_admin_permissions_password_redaction_and_test_button(self):
        self.client.force_login(self.user)
        url = reverse('admin:theatre_emailsettings_change', args=[1])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.config.password_ciphertext)
        self.assertNotContains(response, 'fictional-smtp-password')
        self.assertContains(response, 'Enviar prueba a mi correo')
        self.assertEqual(self.client.post(url, self.config_data(smtp_password='secret-log-test')).status_code, 302)
        self.assertNotIn('secret-log-test', str(list(LogEntry.objects.values_list('change_message', flat=True))))
        test_url = reverse('admin:theatre_emailsettings_test')
        self.assertEqual(self.client.get(test_url).status_code, 405)
        self.assertEqual(self.client.post(test_url).status_code, 302)
        self.assertEqual(EmailNotification.objects.get(event='test').recipient, self.admin.email)

    def test_smtp_error_does_not_affect_reservation_and_disabling_pauses_delivery(self):
        booking = self.booking()
        self.config.enabled = False
        self.config.save()
        with patch('theatre.email_delivery.smtp_connection') as connection:
            self.assertFalse(deliver_one())
            connection.assert_not_called()
        booking.refresh_from_db()
        self.assertFalse(booking.cancelled_at)
        self.assertEqual(EmailNotification.objects.filter(status='pending').count(), 3)


@skipUnless(connection.vendor == 'postgresql', 'Requiere bloqueo de PostgreSQL')
class NotificationConcurrencyTests(TransactionTestCase):
    def test_parallel_delivery_does_not_send_same_pending_message_twice(self):
        config = EmailSettings(enabled=True, host='smtp.example.test', username='fake',
                               from_email='notice@example.test', public_url='https://app.example.test')
        config.set_password('fictional-only')
        config.save()
        EmailNotification.objects.create(event='test', recipient='recipient@example.test', subject='Test',
            body='Test', dedupe_key='0' * 64)
        barrier = Barrier(2)
        sent = []
        class SMTP:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def send_messages(self, messages):
                sent.extend(messages)
                return len(messages)
        def deliver(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_one()
            finally:
                close_old_connections()
        with patch('theatre.email_delivery.smtp_connection', return_value=SMTP()):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(deliver, range(2)))
        self.assertCountEqual(results, [True, False])
        self.assertEqual(len(sent), 1)
        self.assertEqual(EmailNotification.objects.get().status, 'sent')
