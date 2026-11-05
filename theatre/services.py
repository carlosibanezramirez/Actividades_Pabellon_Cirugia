from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Correction, Doctor, Event, Intervention, Procedure, Room


def require_permission(user, permission):
    if not user.is_authenticated or not user.is_active or not user.has_perm(permission):
        raise PermissionDenied


@transaction.atomic
def create_intervention(*, user, room, procedure, doctor):
    require_permission(user, 'theatre.operate_intervention')
    locked_room = Room.objects.select_for_update().get(pk=room.pk)
    if not locked_room.active or not Procedure.objects.get(pk=procedure.pk).active or not Doctor.objects.get(pk=doctor.pk).active:
        raise ValidationError('Seleccione elementos activos de las listas.')
    if Intervention.objects.filter(room=locked_room, completed_at__isnull=True).exists():
        raise ValidationError('Este pabellón ya tiene una intervención en curso. Retómela antes de crear otra.')
    return Intervention.objects.create(room=locked_room, procedure=procedure, doctor=doctor, created_by=user)


@transaction.atomic
def record_event(*, user, intervention_id, stage):
    require_permission(user, 'theatre.operate_intervention')
    intervention = Intervention.objects.select_for_update().get(pk=intervention_id)
    events = list(intervention.events.order_by('stage'))
    if intervention.completed_at or stage != len(events) + 1 or not 1 <= stage <= 9:
        raise ValidationError('El evento ya se registró o no corresponde al siguiente paso. Actualice la página.')
    now = timezone.now()
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
