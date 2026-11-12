from django.db.models import Max, OuterRef, Subquery
from django.utils import timezone

from .models import Event, Intervention, OperatingSettings


def preparation_alarm(room_id, intervention_id, started_at, stage, maximum, now):
    active = bool(stage == Event.Stage.ROOM_START and started_at)
    elapsed = max(0, (now - started_at).total_seconds()) if active else 0
    seconds = int(elapsed)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return {
        'room_id': room_id, 'intervention_id': intervention_id or '',
        'active': active, 'started_at': started_at.isoformat() if active else '',
        'maximum': maximum, 'server_now': now.isoformat(),
        'exceeded': active and elapsed > maximum * 60,
        'elapsed_label': f'{hours:02d}:{minutes:02d}:{seconds:02d}',
    }


def active_preparations(doctor=None):
    policy = OperatingSettings.current()
    now = timezone.now()
    start = Event.objects.filter(intervention_id=OuterRef('pk'), stage=Event.Stage.ROOM_START).values('occurred_at')[:1]
    rows = Intervention.objects.filter(completed_at__isnull=True).annotate(
        stage=Max('events__stage'), started=Subquery(start),
    ).filter(stage=Event.Stage.ROOM_START)
    if doctor:
        rows = rows.filter(doctor=doctor)
    return {
        'now': now.isoformat(), 'maximum_minutes': policy.preparation_max_minutes,
        'active': [{'room_id': item.room_id, 'intervention_id': item.pk, 'started_at': item.started.isoformat()}
                   for item in rows if item.started],
    }
