from datetime import timedelta

from django.utils import timezone

from .models import Event, Reservation, ReservationAdjustment


def save_adjustment(booking, intervention, user, start, planned, end, reason, needs_rescheduling=False):
    from .notifications import reservation_summary, queue_reservation_notification
    previous_summary = reservation_summary(booking)
    was_pending = booking.needs_rescheduling
    previous = (booking.starts_at, booking.planned_start_at, booking.ends_at)
    if booking.original_starts_at is None:
        booking.original_starts_at, booking.original_planned_start_at, booking.original_ends_at = previous
    booking.starts_at, booking.planned_start_at, booking.ends_at = start, planned, end
    booking.timing_adjusted = True
    booking.needs_rescheduling = needs_rescheduling
    booking.save()
    adjustment = ReservationAdjustment.objects.create(reservation=booking, source_intervention=intervention,
        previous_start=previous[0], previous_planned_start=previous[1], previous_end=previous[2],
        new_start=start, new_planned_start=planned, new_end=end, reason=reason, recorded_by=user)

    event = 'reschedule' if needs_rescheduling and not was_pending else 'modified'
    queue_reservation_notification(booking, event, event_key=f'adjustment:{adjustment.pk}', previous_summary=previous_summary)


def reconcile_patient_exit(intervention, exit_at, user):
    """Se ejecuta dentro de la transacción y con el pabellón bloqueado."""
    if not intervention.reservation_id:
        return
    booking = Reservation.objects.select_for_update().get(pk=intervention.reservation_id)
    previous_end = booking.ends_at
    if previous_end == exit_at:
        return
    affected = list(Reservation.objects.select_for_update().filter(
        room_id=booking.room_id, cancelled_at__isnull=True, needs_rescheduling=False,
        starts_at__lt=exit_at, ends_at__gt=previous_end,
    ).exclude(pk=booking.pk).order_by('starts_at', 'pk')) if exit_at > previous_end else []
    if affected:
        booking.overrun_from = min(booking.overrun_from or previous_end, previous_end)
    actual_start = intervention.events.filter(stage=Event.Stage.ROOM_START).first()
    start = min(booking.starts_at, actual_start.occurred_at if actual_start else exit_at, exit_at)
    planned = booking.planned_start_at
    if planned and planned >= exit_at:
        recorded = intervention.events.filter(stage=Event.Stage.ANESTHESIA_PREP_START).first()
        planned = min(recorded.occurred_at if recorded else start, exit_at)
    save_adjustment(booking, intervention, user, start, planned, exit_at, 'Ajuste al horario real de salida del paciente')
    for following in affected:
        preparation = ((following.planned_start_at - following.starts_at)
                       if following.planned_start_at else timedelta(0))
        new_start = min(exit_at, following.ends_at)
        planned = min(max(following.planned_start_at, new_start + preparation), following.ends_at) if following.planned_start_at else None
        insufficient = exit_at >= following.ends_at or (planned is not None and planned >= following.ends_at)
        save_adjustment(following, intervention, user, new_start, planned, following.ends_at,
                        'Tramo reducido por prolongación de la intervención anterior', insufficient)
