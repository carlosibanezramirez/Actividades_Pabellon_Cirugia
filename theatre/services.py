from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Correction, Doctor, Event, Intervention, Procedure, Reservation, Room, PreoperativeActivity


def require_permission(user, permission):
    if not user.is_authenticated or not user.is_active or not user.has_perm(permission):
        raise PermissionDenied


@transaction.atomic
def create_intervention(*, user, room, procedure, doctor, anesthetist, reservation=None):
    require_permission(user, 'theatre.operate_intervention')
    locked_room = Room.objects.select_for_update().get(pk=room.pk)
    if not locked_room.active or not Procedure.objects.get(pk=procedure.pk).active or not Doctor.objects.get(pk=doctor.pk).active:
        raise ValidationError('Seleccione elementos activos de las listas.')
    if not anesthetist or not Doctor.objects.filter(
        pk=anesthetist.pk, active=True, specialty__active=True, specialty__is_anesthesia=True,
    ).exists():
        raise ValidationError('Seleccione un anestesista activo con especialidad habilitada para anestesia.')
    if not reservation and Intervention.objects.filter(room=locked_room, completed_at__isnull=True, room_engaged=True).exists():
        raise ValidationError('Este pabellón ya tiene una intervención en curso. Retómela antes de crear otra.')
    from .scheduling import HOUR
    now = timezone.now()
    if reservation:
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.cancelled_at:
            raise ValidationError('La reserva está cancelada.')
        if (reservation.room_id != locked_room.pk or reservation.doctor_id != doctor.pk
                or reservation.procedure_id != procedure.pk):
            raise ValidationError('El pabellón, médico y tipo de cirugía deben coincidir con la reserva.')
        if now >= reservation.ends_at:
            raise ValidationError('El horario de la reserva ya finalizó.')
        if Intervention.objects.filter(reservation=reservation).exists():
            raise ValidationError('La reserva ya tiene una intervención asociada.')
    expected_end = reservation.ends_at if reservation and reservation.planned_start_at else now + HOUR
    bookings = Reservation.objects.filter(cancelled_at__isnull=True, room=locked_room, starts_at__lt=expected_end, ends_at__gt=now)
    if reservation:
        bookings = bookings.exclude(pk=reservation.pk)
    if not reservation and bookings.exists():
        raise ValidationError('El pabellón tiene una reserva que coincide con la próxima hora. Inicie desde su reserva o use otro horario.')
    return Intervention.objects.create(room=locked_room, procedure=procedure, doctor=doctor, anesthetist=anesthetist, created_by=user, reservation=reservation, room_engaged=reservation is None)


@transaction.atomic
def record_event(*, user, intervention_id, stage):
    require_permission(user, 'theatre.operate_intervention')
    room_id = Intervention.objects.values_list('room_id', flat=True).get(pk=intervention_id)
    Room.objects.select_for_update().get(pk=room_id)
    intervention = Intervention.objects.select_for_update(of=('self',)).select_related('reservation').get(pk=intervention_id)
    events = list(intervention.events.order_by('stage'))
    if intervention.completed_at or stage != len(events) + 1 or not 1 <= stage <= 9:
        raise ValidationError('El evento ya se registró o no corresponde al siguiente paso. Actualice la página.')
    if stage == Event.Stage.ANESTHESIA_PREP_START and intervention.preoperative_activities.count() < 2:
        raise ValidationError('Complete ambos consentimientos informados antes de iniciar la preparación de anestesia.')
    now = timezone.now()
    if intervention.reservation_id:
        booking = intervention.reservation
        if booking.cancelled_at:
            raise ValidationError('La reserva está cancelada.')
        if stage in (Event.Stage.ROOM_START, Event.Stage.ROOM_END) and now < booking.starts_at - timedelta(minutes=30):
            earliest = timezone.localtime(booking.starts_at - timedelta(minutes=30)).strftime('%d/%m/%Y %H:%M')
            raise ValidationError(f'La preparación del pabellón puede registrarse desde {earliest}, 30 minutos antes de su inicio programado.')
        if stage == Event.Stage.ROOM_START:
            if now >= booking.ends_at:
                raise ValidationError('El horario de la reserva ya finalizó.')
            if Reservation.objects.filter(room_id=room_id, cancelled_at__isnull=True,
                    starts_at__lt=booking.ends_at, ends_at__gt=now).exclude(pk=booking.pk).exists():
                raise ValidationError('El tramo anticipado coincide con otra reserva del pabellón.')
    if stage == Event.Stage.ROOM_START:
        if Intervention.objects.filter(room_id=room_id, room_engaged=True, completed_at__isnull=True).exclude(pk=intervention.pk).exists():
            raise ValidationError('Este pabellón ya tiene una intervención en curso.')
        intervention.room_engaged = True
        intervention.save(update_fields=['room_engaged'])
    if stage == Event.Stage.ANESTHESIA_PREP_START and intervention.preoperative_activities.filter(completed_at__gt=now).exists():
        raise ValidationError('La hora del servidor es anterior al registro de los consentimientos.')
    if events and now < events[-1].occurred_at:
        raise ValidationError('La hora del servidor es anterior al último evento. Solicite revisión al administrador.')
    event = Event.objects.create(intervention=intervention, stage=stage, occurred_at=now, original_at=now, recorded_by=user)
    if stage == Event.Stage.PATIENT_EXIT:
        intervention.completed_at = now
        intervention.save(update_fields=['completed_at'])
    return event


@transaction.atomic
def correct_event(*, user, intervention_id, event_id, new_at, reason, expected_at):
    require_permission(user, 'theatre.correct_event')
    intervention = Intervention.objects.select_for_update().get(pk=intervention_id)
    event = intervention.events.get(pk=event_id)
    if event.occurred_at != expected_at:
        raise ValidationError('Otro administrador modificó este evento. Recargue la página antes de corregirlo.')
    reason = reason.strip()
    if not reason:
        raise ValidationError('Debe indicar el motivo de la corrección.')
    if timezone.is_naive(new_at):
        raise ValidationError('La hora debe incluir zona horaria.')
    if new_at > timezone.now():
        raise ValidationError('No se permiten horarios futuros.')
    if new_at < intervention.created_at:
        raise ValidationError('La hora no puede ser anterior a la creación de la intervención.')
    if new_at == event.occurred_at:
        raise ValidationError('La nueva hora debe ser diferente de la actual.')
    if event.stage == Event.Stage.ANESTHESIA_PREP_START and intervention.preoperative_activities.filter(completed_at__gt=new_at).exists():
        raise ValidationError('La preparación de anestesia no puede ser anterior al registro de los consentimientos.')
    if intervention.reservation_id and event.stage in (Event.Stage.ROOM_START, Event.Stage.ROOM_END) and new_at < intervention.reservation.starts_at - timedelta(minutes=30):
        raise ValidationError('La preparación no puede registrarse más de 30 minutos antes de su inicio programado.')
    previous = intervention.events.filter(stage__lt=event.stage).order_by('-stage').first()
    following = intervention.events.filter(stage__gt=event.stage).order_by('stage').first()
    if (previous and new_at < previous.occurred_at) or (following and new_at > following.occurred_at):
        raise ValidationError('La corrección debe respetar el orden temporal de los eventos.')
    Correction.objects.create(event=event, previous_at=event.occurred_at, new_at=new_at, reason=reason, corrected_by=user)
    event.occurred_at = new_at
    event.save(update_fields=['occurred_at'])
    if event.stage == Event.Stage.PATIENT_EXIT:
        intervention.completed_at = new_at
        intervention.save(update_fields=['completed_at'])
    return event


@transaction.atomic
def complete_preoperative_activity(*, user, intervention_id, kind):
    require_permission(user, 'theatre.operate_intervention')
    intervention = Intervention.objects.select_for_update().get(pk=intervention_id)
    if kind not in PreoperativeActivity.Kind.values:
        raise ValidationError('La actividad preoperatoria no es válida.')
    if intervention.completed_at or intervention.events.filter(stage__gte=Event.Stage.ANESTHESIA_PREP_START).exists():
        raise ValidationError('Los consentimientos deben registrarse antes de iniciar la preparación de anestesia.')
    if intervention.preoperative_activities.filter(kind=kind).exists():
        raise ValidationError('Esta actividad ya fue registrada.')
    return PreoperativeActivity.objects.create(intervention=intervention, kind=kind, completed_by=user)
