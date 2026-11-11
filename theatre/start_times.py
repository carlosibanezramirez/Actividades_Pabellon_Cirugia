from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.forms import DateTimeField
from django.utils import timezone

from .models import OperatingSettings


def start_times_for_day(day, now=None):
    now = now or timezone.now()
    earliest = now + timedelta(minutes=OperatingSettings.current().preparation_mean_minutes)
    times = []
    for hour in range(24):
        for minute in (0, 30):
            clock = datetime.min.time().replace(hour=hour, minute=minute)
            try:
                instant = DateTimeField().clean(datetime.combine(day, clock))
            except ValidationError:
                continue
            if instant >= earliest:
                times.append(clock.strftime('%H:%M'))
    return times
