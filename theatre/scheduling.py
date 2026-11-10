from datetime import datetime, time, timedelta, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import Doctor, Event, Intervention, Procedure, Reservation, Room
from .operating import booking_window, validate_booking_window
from .services import require_permission
from .rut import normalize_rut


HOUR = timedelta(hours=1)


def day_slots(day):
    if not 1900 <= day.year <= 9998:
        raise ValidationError('Seleccione una fecha entre los años 1900 y 9998.')
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz).astimezone(datetime_timezone.utc)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), tz).astimezone(datetime_timezone.utc)
    slots = []
    cursor = start
    while cursor + HOUR <= end:
        local_start, local_end = timezone.localtime(cursor), timezone.localtime(cursor + HOUR)
        slots.append({
            'index': len(slots), 'start': cursor, 'end': cursor + HOUR,
            'label': f'{local_start:%H:%M} – {local_end:%H:%M}',
            'offset': local_start.strftime('%z'),
        })
        cursor += HOUR
    return slots


def occupancy(day, now=None, room_id=None, minimum_use=HOUR):
    """Intervalos de reservas y uso real; los límites de término son exclusivos."""
    now = now or timezone.now()
    slots = day_slots(day)
    start, end = slots[0]['start'], slots[-1]['end']
    reservations = Reservation.objects.filter(starts_at__lt=end, ends_at__gt=start).select_related('doctor', 'procedure', 'room', 'created_by', 'intervention')
    uses = Intervention.objects.filter(created_at__lt=end).filter(
        Q(completed_at__isnull=True) | Q(completed_at__gt=start - minimum_use),
    ).select_related('doctor', 'procedure').prefetch_related(Prefetch(
        'events', queryset=Event.objects.filter(stage__in=[1, 2, 9]).order_by('stage'),
    ))
    if room_id is not None:
        reservations = reservations.filter(room_id=room_id)
        uses = uses.filter(room_id=room_id)
    periods = []
    for reservation in reservations:
        periods.append({'room_id': reservation.room_id, 'start': reservation.starts_at,
                        'end': reservation.ends_at, 'state': 'no_disponible',
                        'label': 'Reservado', 'reservation': reservation, 'intervention': None})
    for item in uses:
        events = {event.stage: event.occurred_at for event in item.events.all()}
        actual_start = events.get(1, item.created_at)
        actual_end = events.get(9, item.completed_at)
        if actual_end is None:
            # Sin salida no se promete una hora libre para el resto de hoy.
            # Una intervención abierta no se proyecta indefinidamente sobre días futuros.
            if day > timezone.localdate(now):
                continue
            usage_end = end
        else:
            usage_end = max(actual_end, actual_start + minimum_use)
        if usage_end <= start or actual_start >= end:
            continue
        base = {'room_id': item.room_id, 'reservation': None, 'intervention': item}
        if 1 not in events:
            periods.append({**base, 'start': actual_start, 'end': usage_end,
                            'state': 'no_disponible', 'label': 'Pendiente de preparación'})
            continue
        preparation_end = events.get(2, usage_end)
        if actual_start < preparation_end:
            periods.append({**base, 'start': actual_start, 'end': min(preparation_end, usage_end),
                            'state': 'preparacion', 'label': 'En preparación'})
        if preparation_end < usage_end:
            periods.append({**base, 'start': preparation_end, 'end': usage_end,
                            'state': 'procedimiento', 'label': 'En procedimiento / uso mínimo'})
    return slots, periods


def availability(day, now=None):
    now = now or timezone.now()
    slots, periods = occupancy(day, now)
    priority = {'no_disponible': 1, 'preparacion': 2, 'procedimiento': 3}
    by_room = {}
    reservations = {}
    for period in periods:
        by_room.setdefault(period['room_id'], []).append(period)
        if period['reservation']:
            reservations[period['reservation'].pk] = period['reservation']
    rows = []
    for room in Room.objects.all():
        opening, closing = booking_window(day, room)
        cells = []
        for slot in slots:
            matches = [period for period in by_room.get(room.pk, [])
                       if period['start'] < slot['end'] and period['end'] > slot['start']]
            busy = max(matches, key=lambda p: priority[p['state']]) if matches else None
            state = 'no_disponible' if not room.active else (busy['state'] if busy else 'libre')
            label = 'No disponible' if not room.active else (busy['label'] if busy else 'Libre')
            outside_hours = slot['start'] < opening or slot['end'] > closing
            if room.active and not busy and outside_hours:
                state, label = 'fuera_horario', 'Fuera de horario'
            cells.append({**slot, 'value': f'{room.pk}:{slot["index"]}',
                          'time_label': slot['label'],
                          'state': state, 'label': label,
                          'selectable': room.active and not matches and not outside_hours and slot['start'] >= now,
                          'past': slot['start'] < now,
                          'busy': busy})
        rows.append({'room': room, 'slots': cells})
    return {'rows': rows, 'slots': slots,
            'reservations': sorted(reservations.values(), key=lambda r: (r.starts_at, r.pk))}


@transaction.atomic
def reserve_hours(*, user, day, selections, doctor, procedure, patient_name, patient_rut=''):
    require_permission(user, 'theatre.operate_intervention')
    patient_rut = normalize_rut(patient_rut)
    patient_name = patient_name.strip()
    if not patient_name or len(patient_name) > 180:
        raise ValidationError('Ingrese el nombre del paciente (máximo 180 caracteres).')
    try:
        parsed = [(int(value.split(':')[0]), int(value.split(':')[1])) for value in selections if value.count(':') == 1]
    except (ValueError, AttributeError, TypeError):
        raise ValidationError('La selección de horas no es válida.')
    if not parsed or len(parsed) != len(selections) or len(set(parsed)) != len(parsed):
        raise ValidationError('Seleccione al menos una hora, sin repetir bloques.')
    if len({room_id for room_id, _ in parsed}) != 1:
        raise ValidationError('Seleccione horas de un solo pabellón.')
    room = Room.objects.select_for_update().filter(pk=parsed[0][0], active=True).first()
    if room is None:
        raise ValidationError('El pabellón no está disponible.')
    indexes = sorted(index for _, index in parsed)
    slots = day_slots(day)
    if indexes[0] < 0 or indexes[-1] >= len(slots) or indexes != list(range(indexes[0], indexes[-1] + 1)):
        raise ValidationError('Las horas deben ser consecutivas y pertenecer a la fecha seleccionada.')
    start, end = slots[indexes[0]]['start'], slots[indexes[-1]]['end']
    validate_booking_window(day, start, end, room)
    now = timezone.now()
    if start < now:
        raise ValidationError('No se pueden reservar bloques que ya comenzaron.')
    if not Doctor.objects.filter(pk=doctor.pk, active=True).exists() or not Procedure.objects.filter(pk=procedure.pk, active=True).exists():
        raise ValidationError('Seleccione un médico y un tipo de cirugía activos.')
    _, periods = occupancy(day, now, room.pk)
    if any(period['start'] < end and period['end'] > start for period in periods):
        raise ValidationError('Una o más horas ya no están disponibles. Actualice la agenda y seleccione otras.')
    from .weekly_scheduling import validate_start_gap
    validate_start_gap(room, day, start)
    return Reservation.objects.create(room=room, doctor=doctor, procedure=procedure,
                                      patient_name=patient_name, patient_rut=patient_rut,
                                      starts_at=start, ends_at=end, created_by=user)
