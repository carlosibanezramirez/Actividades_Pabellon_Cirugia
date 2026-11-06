from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.db.models import DateTimeField, Max, OuterRef, Subquery
from django.utils import timezone

from .models import Event, Intervention, Room


STATES = (
    ('libre', 'Libre'),
    ('preparacion', 'En preparación'),
    ('procedimiento', 'En procedimiento'),
    ('no_disponible', 'No disponible'),
)


def duration_label(seconds):
    if seconds is None:
        return '—'
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def room_snapshot():
    opened = {
        item.room_id: item for item in Intervention.objects.filter(completed_at__isnull=True)
        .select_related('procedure', 'doctor', 'anesthetist')
        .annotate(last_stage=Max('events__stage'))
    }
    rows = []
    counts = dict.fromkeys(dict(STATES), 0)
    for room in Room.objects.all():
        intervention = opened.get(room.pk)
        stage = intervention.last_stage if intervention else None
        if not room.active:
            state = 'no_disponible'
        elif not intervention:
            state = 'libre'
        elif stage and stage >= Event.Stage.ANESTHESIA_START:
            state = 'procedimiento'
        else:
            state = 'preparacion'
        counts[state] += 1
        rows.append({
            'room': room, 'state': state, 'state_label': dict(STATES)[state],
            'intervention': intervention,
            'last_event': Event.Stage(stage).label if stage else ('Sin eventos registrados' if intervention else '—'),
        })
    return rows, counts


def event_statistics(start_date, end_date):
    # Dos medianoches locales: incluye el día final completo, incluso con cambios de hora.
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
    period_events = Event.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    previous = Event.objects.filter(
        intervention_id=OuterRef('intervention_id'), stage=OuterRef('stage') - 1,
    ).values('occurred_at')[:1]
    events = period_events.annotate(
        previous_at=Subquery(previous, output_field=DateTimeField()),
    ).order_by().values('stage', 'occurred_at', 'previous_at')
    buckets = {stage: {'stage': stage, 'label': label, 'events': 0, 'samples': 0,
                       'total': 0, 'minimum': None, 'maximum': None, 'invalid': 0}
               for stage, label in Event.Stage.choices}
    for event in events.iterator():
        bucket = buckets[event['stage']]
        bucket['events'] += 1
        if event['previous_at'] is None:
            continue
        duration = (event['occurred_at'] - event['previous_at']).total_seconds()
        if duration < 0:
            bucket['invalid'] += 1
            continue
        bucket['samples'] += 1
        bucket['total'] += duration
        bucket['minimum'] = duration if bucket['minimum'] is None else min(bucket['minimum'], duration)
        bucket['maximum'] = duration if bucket['maximum'] is None else max(bucket['maximum'], duration)
    rows = list(buckets.values())
    for row in rows:
        row['average_seconds'] = row['total'] / row['samples'] if row['samples'] else None
        row['average'] = duration_label(row['average_seconds'])
        row['minimum'] = duration_label(row['minimum'])
        row['maximum'] = duration_label(row['maximum'])
        row['interval'] = f'{row["stage"] - 1} → {row["stage"]}' if row['stage'] > 1 else 'Sin evento anterior'
    maximum_average = max((row['average_seconds'] or 0 for row in rows), default=0)
    for row in rows:
        row['bar_width'] = round(100 * (row['average_seconds'] or 0) / maximum_average) if maximum_average else 0
    return {
        'rows': rows, 'event_count': sum(row['events'] for row in rows),
        'intervention_count': period_events.values('intervention_id').distinct().count(),
        'exit_count': buckets[Event.Stage.PATIENT_EXIT]['events'],
        'invalid_count': sum(row['invalid'] for row in rows),
    }


def state_links(counts, dates, selected):
    return [dict(key=key, label=label, count=counts[key], selected=key == selected,
                 query=urlencode({**dates, 'estado': key})) for key, label in STATES]
