from datetime import datetime, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.utils import timezone


def booking_window(day, room):
    tz = timezone.get_current_timezone()
    opening = timezone.make_aware(datetime.combine(day, room.opening_time), tz).astimezone(datetime_timezone.utc)
    closing = timezone.make_aware(datetime.combine(day, room.closing_time), tz).astimezone(datetime_timezone.utc)
    return opening, closing


def validate_booking_window(day, planned_start, end, room):
    opening, closing = booking_window(day, room)
    if planned_start < opening or planned_start > closing:
        raise ValidationError(
            f'La reserva debe comenzar entre las {room.opening_time:%H:%M} y las '
            f'{room.closing_time:%H:%M}, inclusive. Puede terminar después del cierre '
            'o al día siguiente; la preparación previa puede comenzar antes de la apertura.'
        )
