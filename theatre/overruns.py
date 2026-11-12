from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AutomaticRelocation, Event, Intervention, OperatingSettings, Reservation, Room
from .weekly_scheduling import validate_reservation_space


@transaction.atomic
def relocate_next_reservation(intervention_id, now=None):
    now = now or timezone.now()
    allowed = OperatingSettings.current().allowed_overrun_minutes
    # Orden compartido con los traslados manuales. También serializa dos monitores.
    rooms = list(Room.objects.select_for_update().order_by('pk'))
    source = Intervention.objects.select_for_update().get(pk=intervention_id)
    if not source.reservation_id or source.completed_at or not source.room_engaged:
        return None
    if AutomaticRelocation.objects.filter(source_intervention=source).exists():
        return None
    booking = Reservation.objects.select_for_update().get(pk=source.reservation_id)
    original_room = next(room for room in rooms if room.pk == source.room_id)
    if (booking.cancelled_at or original_room.room_type == Room.Type.EMERGENCY
            or now < booking.ends_at + timedelta(minutes=allowed)
            or not source.events.filter(stage=Event.Stage.SURGERY_START).exists()
            or source.events.filter(stage=Event.Stage.PATIENT_EXIT).exists()):
        return None
    following = Reservation.objects.select_for_update().filter(
        room_id=source.room_id, cancelled_at__isnull=True, needs_rescheduling=False,
        starts_at__gte=booking.ends_at, ends_at__gt=now,
    ).exclude(pk=booking.pk).order_by('starts_at', 'pk').first()
    if following is None:
        return None
    active_intervention = Intervention.objects.select_for_update().filter(reservation=following).first()
    if active_intervention and (active_intervention.room_engaged or active_intervention.completed_at):
        return None
    planned = following.planned_start_at or following.starts_at
    preparation = int((planned - following.starts_at).total_seconds() // 60)
    for target in rooms:
        if not target.active or target.pk == source.room_id or target.room_type != original_room.room_type:
            continue
        try:
            validate_reservation_space(target, timezone.localdate(planned), planned,
                                       following.starts_at, following.ends_at, now, preparation)
        except ValidationError:
            continue
        relocation = AutomaticRelocation.objects.create(source_intervention=source, reservation=following,
            from_room=original_room, to_room=target, starts_at=following.starts_at,
            planned_start_at=following.planned_start_at, ends_at=following.ends_at, allowed_minutes=allowed)
        from .notifications import reservation_summary, queue_reservation_notification
        previous_summary = reservation_summary(following)
        following.room = target
        following.save(update_fields=['room'])
        if active_intervention:
            active_intervention.room = target
            active_intervention.save(update_fields=['room'])
        queue_reservation_notification(following, 'relocated', event_key=f'relocation:{relocation.pk}', previous_summary=previous_summary)
        return relocation
    return None


def process_overruns(now=None):
    now = now or timezone.now()
    candidates = Intervention.objects.filter(completed_at__isnull=True, room_engaged=True,
        reservation__isnull=False, reservation__cancelled_at__isnull=True,
        reservation__ends_at__lte=now, overrun_relocation__isnull=True).values_list('pk', flat=True)
    count = 0
    for pk in list(candidates):
        if relocate_next_reservation(pk, now):
            count += 1
    return count
