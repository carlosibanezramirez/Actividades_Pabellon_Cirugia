from datetime import datetime, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.utils import timezone


def booking_window(day, policy):
    tz = timezone.get_current_timezone()
    opening = timezone.make_aware(datetime.combine(day, policy.opening_time), tz).astimezone(datetime_timezone.utc)
    closing = timezone.make_aware(datetime.combine(day, policy.closing_time), tz).astimezone(datetime_timezone.utc)
    return opening, closing


def validate_booking_window(day, planned_start, end, policy):
    opening, closing = booking_window(day, policy)
    if planned_start < opening or planned_start >= closing or end > closing:
        raise ValidationError(
            f'La reserva debe comenzar desde las {policy.opening_time:%H:%M} y terminar '
            f'a más tardar a las {policy.closing_time:%H:%M}. La preparación previa puede '
            'comenzar antes de la apertura.'
        )
