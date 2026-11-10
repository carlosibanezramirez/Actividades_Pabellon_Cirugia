from datetime import datetime, timedelta, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import DateTimeField
from django.utils import timezone

from .models import Doctor, OperatingSettings, Procedure, Reservation, Room
from .operating import booking_window, validate_booking_window
from .scheduling import day_slots, occupancy
from .services import require_permission
from .rut import normalize_rut


WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MAX_START_GAP = timedelta(minutes=30)


def week_start(day):
    return day - timedelta(days=day.weekday())


def validate_start_gap(room, day, planned):
    day_start = day_slots(day)[0]['start']
    previous = Reservation.objects.filter(
        room=room, ends_at__gt=day_start, ends_at__lte=planned,
    ).order_by('-ends_at', '-pk').first()
    if previous and planned - previous.ends_at > MAX_START_GAP:
        ended = timezone.localtime(previous.ends_at).strftime('%H:%M')
        raise ValidationError(
            f'El procedimiento anterior termina a las {ended}. El inicio solicitado no puede '
            'quedar más de 30 minutos después, y la preparación previa debe estar disponible.'
        )


def available_starts(room, day, now=None, periods=None, policy=None):
    now = now or timezone.now()
    policy = policy or OperatingSettings.current()
    preparation = timedelta(minutes=policy.preparation_mean_minutes)
    opening, closing = booking_window(day, room)
    if not room.active:
        return []
    if periods is None:
        _, periods = occupancy(day, now, room.pk, minimum_use=timedelta(0))
    previous_day = []
    if day > datetime(1900, 1, 1).date():
        _, previous_day = occupancy(day - timedelta(days=1), now, room.pk, minimum_use=timedelta(0))
    all_periods = periods + previous_day
    day_start = day_slots(day)[0]['start']
    bookings = {p['reservation'].pk: p['reservation'] for p in periods if p['reservation']}
    options = []
    for hour in range(24):
        for minute in [0, 30]:
            clock = datetime.min.time().replace(hour=hour, minute=minute)
            try:
                planned = DateTimeField().clean(datetime.combine(day, clock)).astimezone(datetime_timezone.utc)
            except ValidationError:
                continue
            start, end = planned - preparation, planned + timedelta(minutes=1)
            if planned < opening or planned > closing:
                continue
            if start < now or any(p['start'] < end and p['end'] > start for p in all_periods):
                continue
            preceding = [booking for booking in bookings.values() if day_start < booking.ends_at <= planned]
            previous = max(preceding, key=lambda item: (item.ends_at, item.pk)) if preceding else None
            if previous and planned - previous.ends_at > MAX_START_GAP:
                continue
            options.append({'value': clock.strftime('%H:%M'), 'planned': planned,
                            'preparation_start': start, 'previous': previous})
    return options


def continuous_day(room, day, now=None, policy=None):
    now = now or timezone.now()
    policy = policy or OperatingSettings.current()
    opening, closing = booking_window(day, room)
    slots, periods = occupancy(day, now, room.pk, minimum_use=timedelta(0))
    start, end = slots[0]['start'], slots[-1]['end']
    total = (end - start).total_seconds()
    intervals = sorted((max(start, p['start']), min(end, p['end']))
                       for p in periods if p['start'] < end and p['end'] > start)
    merged = []
    for left, right in intervals:
        if right <= left:
            continue
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    if not room.active:
        merged = [(start, end)]
    segments, cursor = [], start
    for left, right in merged:
        if cursor < left:
            segments.append({'start': cursor, 'end': left, 'busy': False})
        segments.append({'start': left, 'end': right, 'busy': True})
        cursor = right
    if cursor < end:
        segments.append({'start': cursor, 'end': end, 'busy': False})
    split_segments = []
    for segment in segments:
        if segment['busy']:
            split_segments.append({**segment, 'closed': False})
            continue
        limits = sorted({segment['start'], segment['end']} | {
            boundary for boundary in [opening, closing] if segment['start'] < boundary < segment['end']
        })
        for left, right in zip(limits, limits[1:]):
            split_segments.append({'start': left, 'end': right, 'busy': False,
                                   'closed': right <= opening or left >= closing})
    segments = split_segments
    for segment in segments:
        # CSS decimal con punto, independiente del formato numérico regional.
        segment['top'] = f'{100 * (segment["start"] - start).total_seconds() / total:.6f}'
        segment['height'] = f'{100 * (segment["end"] - segment["start"]).total_seconds() / total:.6f}'
        segment['label'] = 'Reservado / ocupado' if segment['busy'] else 'Libre'
        if segment['closed']:
            segment['label'] = 'Fuera de horario de reservas'
        if not room.active:
            segment['label'] = 'Pabellón no disponible'
    ticks = [{'position': '0', 'label': timezone.localtime(start).strftime('%H:%M')}]
    tz = timezone.get_current_timezone()
    for hour in range(3, 24, 3):
        tick = timezone.make_aware(datetime.combine(day, datetime.min.time().replace(hour=hour)), tz).astimezone(datetime_timezone.utc)
        ticks.append({'position': f'{100 * (tick - start).total_seconds() / total:.6f}', 'label': f'{hour:02d}:00'})
    ticks.append({'position': '100', 'label': '24:00'})
    bookings = {p['reservation'].pk: p['reservation'] for p in periods if p['reservation']}
    blocks = []
    options = available_starts(room, day, now, periods, policy)
    for segment in segments:
        if not segment['busy'] and not segment['closed']:
            candidates = [option for option in options
                          if (segment['start'] <= option['preparation_start'] or
                              (segment['start'] == opening and option['planned'] >= opening))
                          and option['planned'] + timedelta(minutes=1) <= segment['end']]
            chained = [option for option in candidates if option['previous']]
            segment['suggested_time'] = chained[0]['value'] if chained else ''
            segment['has_start'] = bool(candidates)
    for booking in sorted(bookings.values(), key=lambda item: (item.starts_at, item.pk)):
        left, right = max(start, booking.starts_at), min(end, booking.ends_at)
        if left < right:
            parts = []
            if booking.planned_start_at:
                prep_end = min(end, booking.planned_start_at)
                if left < prep_end:
                    parts.append({'start': left, 'end': prep_end, 'preparation': True})
                procedure_start = max(start, booking.planned_start_at)
            else:
                procedure_start = left
            if procedure_start < right:
                parts.append({'start': procedure_start, 'end': right, 'preparation': False})
            for part in parts:
                part['top'] = f'{100 * (part["start"] - start).total_seconds() / total:.6f}'
                part['height'] = f'{100 * (part["end"] - part["start"]).total_seconds() / total:.6f}'
                part['compact'] = (part['end'] - part['start']).total_seconds() <= 90 * 60
            blocks.append({
                'booking': booking,
                'top': f'{100 * (left - start).total_seconds() / total:.6f}',
                'height': f'{100 * (right - left).total_seconds() / total:.6f}',
                'compact': (right - left).total_seconds() <= 90 * 60,
                'parts': parts,
                'reservation_start': booking.planned_start_at or booking.starts_at,
                'duration_minutes': int((booking.ends_at - (booking.planned_start_at or booking.starts_at)).total_seconds() // 60),
                'total_duration_minutes': int((booking.ends_at - booking.starts_at).total_seconds() // 60),
            })
    return {
        'date': day, 'weekday': WEEKDAYS[day.weekday()], 'segments': segments,
        'ticks': ticks, 'hours': int(total // 3600), 'active': room.active,
        'free_minutes': int(sum((s['end'] - s['start']).total_seconds() for s in segments if not s['busy'] and not s['closed']) // 60),
        'bookings': sorted(bookings.values(), key=lambda booking: (booking.starts_at, booking.pk)),
        'booking_blocks': blocks,
        'start_options': options,
        'policy': policy,
    }


@transaction.atomic
def reserve_continuous(*, user, room, day, desired_time, duration_minutes, doctor, procedure, patient_name, patient_rut=''):
    require_permission(user, 'theatre.operate_intervention')
    patient_rut = normalize_rut(patient_rut)
    if not 1900 <= day.year <= 9997:
        raise ValidationError('Seleccione una fecha entre los años 1900 y 9997.')
    if desired_time.minute not in (0, 30) or desired_time.second or desired_time.microsecond or desired_time.tzinfo:
        raise ValidationError('El inicio solicitado debe ser a la hora o media hora: por ejemplo, 09:00 o 09:30.')
    if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 1440:
        raise ValidationError('La duración debe ser un número entero entre 1 y 1440 minutos.')
    # Django rechaza horas ambiguas o inexistentes durante cambios de horario.
    planned = DateTimeField().clean(datetime.combine(day, desired_time)).astimezone(datetime_timezone.utc)
    policy = OperatingSettings.current()
    start, end = planned - timedelta(minutes=policy.preparation_mean_minutes), planned + timedelta(minutes=duration_minutes)
    now = timezone.now()
    if start < now:
        raise ValidationError(f'El inicio de preparación ({policy.preparation_mean_minutes} minutos antes) no puede estar en el pasado.')
    patient_name = patient_name.strip()
    if not patient_name or len(patient_name) > 180:
        raise ValidationError('Ingrese el nombre del paciente (máximo 180 caracteres).')
    locked_room = Room.objects.select_for_update().filter(pk=room.pk, active=True).first()
    if locked_room is None:
        raise ValidationError('El pabellón no está disponible.')
    validate_booking_window(day, planned, end, locked_room)
    if not Doctor.objects.filter(pk=doctor.pk, active=True).exists() or not Procedure.objects.filter(pk=procedure.pk, active=True).exists():
        raise ValidationError('Seleccione un médico y un tipo de cirugía activos.')
    cursor = timezone.localdate(start)
    last_day = timezone.localdate(end)
    while cursor <= last_day:
        _, periods = occupancy(cursor, now, locked_room.pk, minimum_use=timedelta(0))
        if any(period['start'] < end and period['end'] > start for period in periods):
            raise ValidationError(f'No hay espacio para el intervalo completo, incluidos los {policy.preparation_mean_minutes} minutos previos de preparación. Elija otro horario.')
        cursor += timedelta(days=1)
    validate_start_gap(locked_room, day, planned)
    return Reservation.objects.create(
        room=locked_room, doctor=doctor, procedure=procedure, patient_name=patient_name, patient_rut=patient_rut,
        starts_at=start, planned_start_at=planned, ends_at=end, created_by=user,
    )
