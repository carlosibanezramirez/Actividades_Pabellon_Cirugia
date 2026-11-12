import hashlib
from datetime import timedelta

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import EmailNotification, EmailSettings, Reservation
from .notifications import doctor_email, reservation_summary


def reminder_booking_valid(booking, now):
    if not booking.doctor.active or booking.cancelled_at or booking.needs_rescheduling:
        return False
    if (booking.planned_start_at or booking.starts_at) <= now:
        return False
    intervention = getattr(booking, 'intervention', None)
    return not intervention or (not intervention.completed_at and not intervention.events.filter(stage__gte=3).exists())


def reminder_body(booking, config):
    return (f'Recordatorio de asistencia a intervención\nReserva #{booking.pk}\n\n'
            f'{reservation_summary(booking)}\n\nHorario de Chile (America/Santiago).\n'
            'Le recordamos su asistencia al pabellón indicado.\n'
            'Consulte su agenda (requiere iniciar sesión):\n' +
            config.public_url.rstrip('/') + reverse('notification_reservation', args=[booking.pk]))


def queue_reminders(now=None):
    now = now or timezone.now()
    config = EmailSettings.objects.filter(pk=1, enabled=True, notify_reminder=True).first()
    if config is None:
        return 0
    horizon = now + timedelta(minutes=config.reminder_minutes)
    bookings = Reservation.objects.filter(cancelled_at__isnull=True, needs_rescheduling=False, doctor__active=True).filter(
        Q(planned_start_at__gt=now, planned_start_at__lte=horizon) |
        Q(planned_start_at__isnull=True, starts_at__gt=now, starts_at__lte=horizon)
    ).select_related('room', 'doctor__user', 'intervention')
    count = 0
    for booking in bookings:
        address = doctor_email(booking.doctor)
        if not address or not reminder_booking_valid(booking, now):
            continue
        planned = booking.planned_start_at or booking.starts_at
        key = hashlib.sha256(f'reminder:{booking.pk}:{planned.isoformat()}:{address}'.encode()).hexdigest()
        _, created = EmailNotification.objects.get_or_create(dedupe_key=key, defaults={
            'reservation': booking, 'event': 'reminder', 'recipient': address,
            'scheduled_start_at': planned, 'subject': f'Surgeon · Recordatorio de intervención · Reserva #{booking.pk}',
            'body': reminder_body(booking, config),
        })
        count += created
    return count


def refresh_reminder(notification, config, now):
    booking = Reservation.objects.select_related('room', 'doctor__user', 'intervention').get(pk=notification.reservation_id)
    if (not reminder_booking_valid(booking, now) or
            (booking.planned_start_at or booking.starts_at) != notification.scheduled_start_at or
            doctor_email(booking.doctor) != notification.recipient):
        notification.status = 'skipped'
        notification.last_error = 'Recordatorio omitido: reserva modificada, cancelada, iniciada, vencida o destinatario actualizado.'
        notification.save(update_fields=['status', 'last_error'])
        return False
    notification.body = reminder_body(booking, config)
    return True
