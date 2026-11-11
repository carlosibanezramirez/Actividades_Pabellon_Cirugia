from datetime import time, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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


class OperatingSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    preparation_mean_minutes = models.PositiveIntegerField(
        'Tiempo medio de preparación (minutos)', default=15,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text='Se agrega antes del inicio solicitado en nuevas reservas. Las reservas existentes conservan sus horarios.',
    )
    preparation_max_minutes = models.PositiveIntegerField(
        'Tiempo máximo de preparación (minutos)', default=30,
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text='Se activa una alarma visual cuando la preparación real en curso supera este tiempo.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'configuración de pabellones'
        verbose_name_plural = 'configuración de pabellones'
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name='single_operating_settings'),
            models.CheckConstraint(condition=Q(preparation_mean_minutes__gte=1, preparation_mean_minutes__lte=1440), name='valid_preparation_mean'),
            models.CheckConstraint(condition=Q(preparation_max_minutes__gte=models.F('preparation_mean_minutes'), preparation_max_minutes__lte=1440), name='valid_preparation_max'),
        ]

    def clean(self):
        super().clean()
        if self.preparation_max_minutes is not None and self.preparation_mean_minutes is not None and self.preparation_max_minutes < self.preparation_mean_minutes:
            raise ValidationError({'preparation_max_minutes': 'El máximo debe ser igual o mayor al tiempo medio.'})

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return 'Configuración general de pabellones'


class Room(Catalog):
    opening_time = models.TimeField('Hora de apertura de reservas', default=time(7))
    closing_time = models.TimeField('Hora de cierre de reservas', default=time(23))

    class Meta(Catalog.Meta):
        verbose_name = 'pabellón'
        verbose_name_plural = 'pabellones'
        constraints = [models.CheckConstraint(condition=Q(closing_time__gt=models.F('opening_time')), name='valid_room_booking_hours')]

    def clean(self):
        super().clean()
        if self.opening_time is not None and self.closing_time is not None and self.opening_time >= self.closing_time:
            raise ValidationError({'closing_time': 'El cierre debe ser posterior a la apertura dentro del mismo día.'})
        for field in ['opening_time', 'closing_time']:
            value = getattr(self, field)
            if value is not None and (value.second or value.microsecond):
                raise ValidationError({field: 'Ingrese horas y minutos, sin segundos.'})


class Procedure(Catalog):
    class Meta(Catalog.Meta):
        verbose_name = 'tipo de operación'
        verbose_name_plural = 'tipos de operación'


class Specialty(Catalog):
    is_anesthesia = models.BooleanField(
        'Habilita como anestesista', default=False,
        help_text='Los médicos activos con esta especialidad podrán seleccionarse como anestesistas.',
    )

    class Meta(Catalog.Meta):
        verbose_name = 'especialidad'
        verbose_name_plural = 'especialidades'


class Doctor(Catalog):
    specialty = models.ForeignKey(
        Specialty, verbose_name='Especialidad', on_delete=models.PROTECT,
        blank=True, null=True,
    )

    class Meta(Catalog.Meta):
        verbose_name = 'médico'
        verbose_name_plural = 'médicos'


class CancellationReason(Catalog):
    class Meta:
        verbose_name = 'causa de cancelación'
        verbose_name_plural = 'causas de cancelación'


class Reservation(models.Model):
    room = models.ForeignKey(Room, verbose_name='Pabellón', on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, verbose_name='Médico solicitante', on_delete=models.PROTECT)
    procedure = models.ForeignKey(Procedure, verbose_name='Tipo de cirugía', on_delete=models.PROTECT)
    patient_name = models.CharField('Nombre del paciente', max_length=180)
    patient_rut = models.CharField('RUT del paciente', max_length=12, blank=True)
    diagnosis = models.TextField('Diagnóstico', blank=True, default='')
    starts_at = models.DateTimeField('Inicio reservado', db_index=True)
    ends_at = models.DateTimeField('Término reservado', db_index=True)
    planned_start_at = models.DateTimeField('Inicio solicitado (preparación de anestesia)', null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    cancelled_at = models.DateTimeField('Fecha de cancelación', null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Cancelada por',
                                     related_name='cancelled_reservations', on_delete=models.PROTECT, null=True, blank=True)
    cancellation_reason = models.ForeignKey(CancellationReason, verbose_name='Causa de cancelación',
                                           on_delete=models.PROTECT, null=True, blank=True)
    cancellation_reason_name = models.CharField('Causa registrada', max_length=180, blank=True)

    class Meta:
        ordering = ['starts_at', 'pk']
        verbose_name = 'reserva'
        verbose_name_plural = 'reservas'
        constraints = [models.CheckConstraint(
            condition=(
                Q(planned_start_at__isnull=True, ends_at__gte=models.F('starts_at') + timedelta(hours=1))
                | Q(planned_start_at__isnull=False,
                    starts_at__lte=models.F('planned_start_at') - timedelta(minutes=1),
                    ends_at__gte=models.F('planned_start_at') + timedelta(minutes=1))
            ),
            name='reservation_valid_timing',
        )]

    @property
    def planned_duration_minutes(self):
        if self.planned_start_at:
            return int((self.ends_at - self.planned_start_at).total_seconds() // 60)
        return None

    @property
    def preparation_minutes(self):
        if self.planned_start_at:
            return int((self.planned_start_at - self.starts_at).total_seconds() // 60)
        return None

    def __str__(self):
        return f'Reserva #{self.pk} · {self.room}'


class Intervention(models.Model):
    reservation = models.OneToOneField(
        Reservation, verbose_name='Reserva', related_name='intervention',
        null=True, blank=True, on_delete=models.PROTECT,
    )
    room = models.ForeignKey(Room, verbose_name='Pabellón', on_delete=models.PROTECT)
    procedure = models.ForeignKey(Procedure, verbose_name='Tipo de operación', on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, verbose_name='Médico principal', on_delete=models.PROTECT)
    anesthetist = models.ForeignKey(
        Doctor, verbose_name='Anestesista', related_name='anesthesia_interventions',
        on_delete=models.PROTECT, null=True,
    )
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
    occurred_at = models.DateTimeField('Hora del evento', db_index=True)
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
