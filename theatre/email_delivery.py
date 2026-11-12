import smtplib
import ssl
from datetime import timedelta
from email.utils import formataddr

from cryptography.fernet import InvalidToken
from django.core.mail import EmailMessage, get_connection
from django.db import connection, transaction
from django.utils import timezone

from .models import EmailNotification, EmailSettings

RETRY_MINUTES = (1, 5, 15, 60)


def smtp_connection(config):
    mode = config.resolved_connection_type
    return get_connection('django.core.mail.backends.smtp.EmailBackend', host=config.host, port=config.port,
                          username=config.username, password=config.get_password(), use_tls=mode == EmailSettings.ConnectionType.STARTTLS,
                          use_ssl=mode == EmailSettings.ConnectionType.TLS,
                          timeout=15, fail_silently=False)


def delivery_error(error):
    if isinstance(error, InvalidToken):
        return 'No se pudo descifrar la contraseña SMTP. Vuelva a ingresarla en Administración.'
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return 'Autenticación SMTP rechazada. Revise usuario y contraseña.'
    if isinstance(error, ssl.SSLError):
        return 'Error TLS al conectar con el servidor SMTP.'
    if isinstance(error, smtplib.SMTPException):
        return 'El servidor SMTP rechazó o interrumpió el envío.'
    if isinstance(error, (OSError, TimeoutError)):
        return 'No se pudo conectar con el servidor SMTP o se agotó el tiempo de espera.'
    return 'No se pudo enviar la notificación. Revise la configuración de correo.'


@transaction.atomic
def deliver_one(now=None):
    now = now or timezone.now()
    config = EmailSettings.objects.filter(pk=1, enabled=True).first()
    if config is None:
        return False
    queryset = EmailNotification.objects.filter(status='pending', next_attempt_at__lte=now).order_by('created_at', 'pk')
    queryset = queryset.select_for_update(skip_locked=True) if connection.vendor == 'postgresql' else queryset.select_for_update()
    notification = queryset.first()
    if notification is None:
        return False
    notification.attempts += 1
    try:
        with smtp_connection(config) as smtp:
            message = EmailMessage(notification.subject, notification.body,
                                   formataddr((config.from_name, config.from_email)),
                                   to=[notification.recipient], connection=smtp,
                                   headers={'Message-ID': f'<{notification.dedupe_key}@{config.from_email.rsplit("@", 1)[-1]}>'})
            if message.send(fail_silently=False) != 1:
                raise smtplib.SMTPException('No messages accepted')
    except Exception as error:
        # Nunca guardar ni imprimir respuestas SMTP que puedan contener credenciales.
        notification.last_error = delivery_error(error)
        if notification.attempts >= 5:
            notification.status = 'failed'
        else:
            notification.next_attempt_at = now + timedelta(minutes=RETRY_MINUTES[notification.attempts - 1])
    else:
        notification.status = 'sent'
        notification.sent_at = timezone.now()
        notification.last_error = ''
    notification.save(update_fields=['attempts', 'status', 'next_attempt_at', 'last_error', 'sent_at'])
    return True


def deliver_pending(limit=20):
    count = 0
    for _ in range(limit):
        if not deliver_one():
            break
        count += 1
    return count
