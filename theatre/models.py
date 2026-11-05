from django.conf import settings
from django.db import models
from django.db.models import Q


class Catalog(models.Model):
    name = models.CharField('Nombre', max_length=160, unique=True)
    active = models.BooleanField('Activo', default=True)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class Room(Catalog):
    class Meta(Catalog.Meta):
        verbose_name = 'pabellón'
        verbose_name_plural = 'pabellones'


class Procedure(Catalog):
    class Meta(Catalog.Meta):
        verbose_name = 'tipo de operación'
        verbose_name_plural = 'tipos de operación'


class Doctor(Catalog):
    class Meta(Catalog.Meta):
        verbose_name = 'médico'
        verbose_name_plural = 'médicos'


class Intervention(models.Model):
    room = models.ForeignKey(Room, verbose_name='Pabellón', on_delete=models.PROTECT)
    procedure = models.ForeignKey(Procedure, verbose_name='Tipo de operación', on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, verbose_name='Médico principal', on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [('operate_intervention', 'Puede registrar intervenciones y eventos'), ('correct_event', 'Puede corregir horarios con auditoría')]
        constraints = [models.UniqueConstraint(fields=['room'], condition=Q(completed_at__isnull=True), name='one_open_intervention_per_room')]

    def __str__(self):
        return f'Intervención #{self.pk} · {self.room}'


class Event(models.Model):
    class Stage(models.IntegerChoices):
        ROOM_START = 1, 'Inicio de preparación del pabellón'
        ROOM_END = 2, 'Término de preparación del pabellón'
        ANESTHESIA_PREP_START = 3, 'Inicio de preparación de la anestesia'
        ANESTHESIA_PREP_END = 4, 'Término de preparación de la anestesia'
        ANESTHESIA_START = 5, 'Inicio del procedimiento de anestesia'
        SURGERY_START = 6, 'Inicio de la cirugía'
        SURGERY_END = 7, 'Término de la cirugía'
        ANESTHESIA_END = 8, 'Término del proceso de anestesia'
        PATIENT_EXIT = 9, 'Salida del paciente del pabellón'

    intervention = models.ForeignKey(Intervention, related_name='events', on_delete=models.PROTECT)
    stage = models.PositiveSmallIntegerField(choices=Stage.choices)
    occurred_at = models.DateTimeField('Hora del evento')
    original_at = models.DateTimeField('Hora original')
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ['stage']
        constraints = [
            models.UniqueConstraint(fields=['intervention', 'stage'], name='unique_intervention_stage'),
            models.CheckConstraint(condition=Q(stage__gte=1, stage__lte=9), name='valid_stage'),
        ]


class Correction(models.Model):
    event = models.ForeignKey(Event, related_name='corrections', on_delete=models.PROTECT)
    previous_at = models.DateTimeField('Hora anterior')
    new_at = models.DateTimeField('Hora corregida')
    reason = models.TextField('Motivo')
    corrected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    corrected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['corrected_at', 'pk']
