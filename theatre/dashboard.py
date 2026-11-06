from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.db.models import Case, DateTimeField, IntegerField, Max, OuterRef, Subquery, Value, When
from django.utils import timezone

from .models import Event, Intervention, Room


STATES = (
    ('libre', 'Libre'),
    ('preparacion', 'En preparación'),
    ('procedimiento', 'En procedimiento'),
    ('no_disponible', 'No disponible'),
)

# Cada medición tiene su propio inicio y término; anestesia incluye la cirugía.
INTERVALS = (
    ('preparacion_pabellon', 'Preparación de pabellón', 1, 2,
     'Inicio → término de la preparación del pabellón (aseo y preparación).'),
    ('inicio_procedimientos', 'Inicio de procedimientos', 2, 3,
     'Término de preparación del pabellón → inicio de preparación de la anestesia.'),
    ('preparacion_anestesia', 'Preparación de anestesia', 3, 4,
     'Inicio → término de la preparación de anestesia.'),
    ('anestesia', 'Anestesia', 5, 8,
     'Inicio del procedimiento de anestesia → término del proceso de anestesia.'),
    ('cirugia', 'Cirugía', 6, 7,
     'Inicio → término de la cirugía.'),
    ('salida_paciente', 'Salida del paciente', 8, 9,
     'Término de anestesia → salida del paciente (reacción del personal de traslado).'),
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
        reason = ''
        if not room.active:
            state = 'no_disponible'
            reason = 'Desactivado en Administración'
        elif not intervention:
            state = 'libre'
        elif stage == Event.Stage.ROOM_START:
            state = 'preparacion'
        elif stage and stage >= Event.Stage.ROOM_END:
            state = 'procedimiento'
        else:
            state = 'no_disponible'
            reason = 'Intervención reservada, pendiente de inicio de preparación'
        counts[state] += 1
        rows.append({
            'room': room, 'state': state, 'state_label': dict(STATES)[state],
            'intervention': intervention,
            'state_reason': reason,
            'last_event': Event.Stage(stage).label if stage else ('Sin eventos registrados' if intervention else '—'),
        })
    return rows, counts


def event_statistics(start_date, end_date):
    # Dos medianoches locales: incluye el día final completo, incluso con cambios de hora.
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz)
    period_events = Event.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    starts = Case(
        *(When(stage=end_stage, then=Value(start_stage)) for _, _, start_stage, end_stage, _ in INTERVALS),
        default=Value(0), output_field=IntegerField(),
    )
    previous = Event.objects.filter(
        intervention_id=OuterRef('intervention_id'), stage=OuterRef('interval_start'),
    ).values('occurred_at')[:1]
    events = period_events.annotate(interval_start=starts).annotate(
        previous_at=Subquery(previous, output_field=DateTimeField()),
    ).order_by().values('stage', 'occurred_at', 'previous_at')
    buckets = {end_stage: {
        'key': key, 'label': label, 'start_stage': start_stage, 'stage': end_stage,
        'description': description, 'events': 0, 'samples': 0, 'total': 0,
        'minimum': None, 'maximum': None, 'invalid': 0,
    } for key, label, start_stage, end_stage, description in INTERVALS}
    event_count = 0
    for event in events.iterator():
        event_count += 1
        if event['stage'] not in buckets:
            continue
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
        row['interval'] = f'{row["start_stage"]} → {row["stage"]}'
    maximum_average = max((row['average_seconds'] or 0 for row in rows), default=0)
    for row in rows:
        row['bar_width'] = round(100 * (row['average_seconds'] or 0) / maximum_average) if maximum_average else 0
    return {
        'rows': rows, 'event_count': event_count,
        'intervention_count': period_events.values('intervention_id').distinct().count(),
        'exit_count': buckets[Event.Stage.PATIENT_EXIT]['events'],
        'invalid_count': sum(row['invalid'] for row in rows),
    }


def state_links(counts, dates, selected):
    return [dict(key=key, label=label, count=counts[key], selected=key == selected,
                 query=urlencode({**dates, 'estado': key})) for key, label in STATES]
