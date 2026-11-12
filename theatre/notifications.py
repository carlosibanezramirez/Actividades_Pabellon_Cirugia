import hashlib
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import Doctor, EmailNotification, EmailSettings

LABELS = {
    'confirmed': 'Reserva confirmada', 'modified': 'Reserva modificada',
    'cancelled': 'Reserva cancelada', 'relocated': 'Reasignación automática de pabellón',
    'reschedule': 'Reserva pendiente de reprogramación',
}


def doctor_email(doctor):
    address = doctor.email or (doctor.user.email if doctor.user_id and doctor.user.is_active else '')
    address = address.strip().lower()
    try:
        validate_email(address)
    except ValidationError:
        return ''
    return address


def recipient_addresses(booking):
    administrators = get_user_model().objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(groups__name='Administrador'),
    ).exclude(email='').values_list('email', flat=True).distinct()
    doctor = Doctor.objects.get(pk=booking.doctor_id)
    creator = get_user_model().objects.get(pk=booking.created_by_id)
    addresses = [doctor_email(doctor), creator.email if creator.is_active else '', *administrators]
    valid = set()
    for address in addresses:
        address = address.strip().lower()
        try:
            validate_email(address)
        except ValidationError:
            continue
        valid.add(address)
    return sorted(valid)


def reservation_summary(booking):
    def clock(instant):
        return timezone.localtime(instant).strftime('%d/%m/%Y %H:%M')
    return (f'Pabellón: {booking.room.name}\n'
            f'Preparación desde: {clock(booking.starts_at)}\n'
            f'Inicio programado: {clock(booking.planned_start_at or booking.starts_at)}\n'
            f'Término programado: {clock(booking.ends_at)}')


def queue_reservation_notification(booking, event, *, event_key=None, previous_summary=''):
    config = EmailSettings.objects.filter(pk=1, enabled=True).first()
    if config is None or not getattr(config, 'notify_' + event):
        return 0
    label = LABELS[event]
    body = f'{label}\nReserva #{booking.pk}\n\n{reservation_summary(booking)}\n'
    if previous_summary:
        body += f'\nHorario/pabellón anterior:\n{previous_summary}\n'
    if event == 'cancelled':
        body += '\nEl motivo de cancelación está disponible en la aplicación.\n'
    if event == 'reschedule':
        body += '\nLa reserva quedó sin tiempo útil por un atraso previo y debe reprogramarse.\n'
    body += '\nConsulte los detalles en la aplicación (requiere iniciar sesión):\n'
    body += config.public_url.rstrip('/') + reverse('notification_reservation', args=[booking.pk])
    key = event_key or uuid.uuid4().hex
    queued = 0
    for address in recipient_addresses(booking):
        dedupe = hashlib.sha256(f'{event}:{key}:{address}'.encode()).hexdigest()
        _, created = EmailNotification.objects.get_or_create(dedupe_key=dedupe, defaults={
            'reservation': booking, 'event': event, 'recipient': address,
            'subject': f'Surgeon · {label} · Reserva #{booking.pk}', 'body': body,
        })
        queued += created
    return queued


def queue_test_email(config, recipient):
    validate_email(recipient)
    return EmailNotification.objects.create(event='test', dedupe_key=uuid.uuid4().hex,
        recipient=recipient, subject='Surgeon · Prueba de correo',
        body='Este es un correo de prueba de las notificaciones de Surgeon.')
