from datetime import time, timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


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
    allowed_overrun_minutes = models.PositiveIntegerField(
        'Tiempo de alargue permitido', default=10, validators=[MinValueValidator(0), MaxValueValidator(1440)],
        help_text='Minutos después del término programado para buscar otro pabellón para la siguiente reserva.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'configuración de pabellones'
        verbose_name_plural = 'configuración de pabellones'
        constraints = [
            models.CheckConstraint(condition=Q(allowed_overrun_minutes__gte=0, allowed_overrun_minutes__lte=1440), name='valid_allowed_overrun'),
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
    class Type(models.TextChoices):
        EMERGENCY = 'emergency', 'Pabellón Urgencias'
        MAJOR = 'major', 'Pabellón Cirugías Mayores'
        MINOR = 'minor', 'Pabellón Cirugías Menores'

    room_type = models.CharField('Tipo de pabellón', max_length=12, choices=Type.choices, default=Type.MAJOR)
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
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name='Cuenta de acceso del médico',
                                related_name='doctor_profile', null=True, blank=True, on_delete=models.PROTECT)
    email = models.EmailField('Correo electrónico', blank=True)
    mobile_phone = models.CharField('Teléfono móvil (SMS y WhatsApp)', max_length=30, blank=True,
                                    help_text='Incluya el código de país, por ejemplo +56912345678.')
    alternate_phone = models.CharField('Teléfono alternativo', max_length=30, blank=True)
    specialty = models.ForeignKey(
        Specialty, verbose_name='Especialidad', on_delete=models.PROTECT,
        blank=True, null=True,
    )

    class Meta(Catalog.Meta):
        verbose_name = 'médico'
        verbose_name_plural = 'médicos'
        permissions = [('view_own_agenda', 'Puede consultar su propia agenda médica')]


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
    planned_start_at = models.DateTimeField('Inicio solicitado (preparación de anestesia)', null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    cancelled_at = models.DateTimeField('Fecha de cancelación', null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Cancelada por',
                                     related_name='cancelled_reservations', on_delete=models.PROTECT, null=True, blank=True)
    cancellation_reason = models.ForeignKey(CancellationReason, verbose_name='Causa de cancelación',
                                           on_delete=models.PROTECT, null=True, blank=True)
    cancellation_reason_name = models.CharField('Causa registrada', max_length=180, blank=True)

    timing_adjusted = models.BooleanField('Horario ajustado por uso real', default=False)
    needs_rescheduling = models.BooleanField('Pendiente de reprogramación', default=False)
    overrun_from = models.DateTimeField('Inicio del alargue con conflicto', null=True, blank=True)
    original_starts_at = models.DateTimeField('Inicio anterior al ajuste automático', null=True, blank=True)
    original_planned_start_at = models.DateTimeField('Inicio solicitado anterior al ajuste', null=True, blank=True)
    original_ends_at = models.DateTimeField('Término anterior al ajuste automático', null=True, blank=True)

    class Meta:
        ordering = ['starts_at', 'pk']
        verbose_name = 'reserva'
        verbose_name_plural = 'reservas'
        constraints = [models.CheckConstraint(
            condition=(
                Q(timing_adjusted=True, ends_at__gte=models.F('starts_at'))
                | Q(timing_adjusted=False, planned_start_at__isnull=True, ends_at__gte=models.F('starts_at') + timedelta(hours=1))
                | Q(timing_adjusted=False, planned_start_at__isnull=False,
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
    room_engaged = models.BooleanField('Uso físico del pabellón iniciado', default=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [('operate_intervention', 'Puede registrar intervenciones y eventos'), ('correct_event', 'Puede corregir horarios con auditoría')]
        constraints = [models.UniqueConstraint(fields=['room'], condition=Q(completed_at__isnull=True, room_engaged=True), name='one_open_intervention_per_room')]

    def __str__(self):
        return f'Intervención #{self.pk} · {self.room}'


class AutomaticRelocation(models.Model):
    source_intervention = models.OneToOneField(Intervention, on_delete=models.PROTECT, related_name='overrun_relocation')
    reservation = models.ForeignKey(Reservation, related_name='automatic_relocations', on_delete=models.PROTECT)
    from_room = models.ForeignKey(Room, related_name='+', on_delete=models.PROTECT)
    to_room = models.ForeignKey(Room, related_name='+', on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    planned_start_at = models.DateTimeField(null=True)
    ends_at = models.DateTimeField()
    allowed_minutes = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at', '-pk']
        verbose_name = 'reasignación automática por alargue'
        verbose_name_plural = 'reasignaciones automáticas por alargue'


class ReservationAdjustment(models.Model):
    reservation = models.ForeignKey(Reservation, related_name='adjustments', on_delete=models.PROTECT)
    source_intervention = models.ForeignKey(Intervention, on_delete=models.PROTECT)
    previous_start = models.DateTimeField()
    previous_planned_start = models.DateTimeField(null=True)
    previous_end = models.DateTimeField()
    new_start = models.DateTimeField()
    new_planned_start = models.DateTimeField(null=True)
    new_end = models.DateTimeField()
    reason = models.CharField(max_length=180)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['recorded_at', 'pk']
        verbose_name = 'ajuste de reserva por uso real'
        verbose_name_plural = 'ajustes de reservas por uso real'


class PreoperativeActivity(models.Model):
    class Kind(models.TextChoices):
        OPERATION_CONSENT = 'operation', 'Firma Consentimiento Informado Operación'
        ANESTHESIA_CONSENT = 'anesthesia', 'Firma Consentimiento Informado Anestesia'

    intervention = models.ForeignKey(Intervention, related_name='preoperative_activities', on_delete=models.PROTECT)
    kind = models.CharField('Actividad', max_length=12, choices=Kind.choices)
    completed_at = models.DateTimeField('Fecha y hora de ejecución', auto_now_add=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Registrada por', on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'actividad preoperatoria'
        verbose_name_plural = 'actividades preoperatorias'
        constraints = [
            models.UniqueConstraint(fields=['intervention', 'kind'], name='unique_preoperative_activity'),
            models.CheckConstraint(condition=Q(kind__in=['operation', 'anesthesia']), name='valid_preoperative_activity'),
        ]


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


class EmailSettings(models.Model):
    class ConnectionType(models.TextChoices):
        AUTO = 'auto', 'Automático según puerto'
        STARTTLS = 'starttls', 'STARTTLS'
        TLS = 'tls', 'TLS / SSL implícito'
        PLAIN = 'plain', 'Sin SSL/TLS (sin cifrado)'

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField('Activar notificaciones por correo', default=False)
    host = models.CharField('Servidor de correos (FQDN)', max_length=253, blank=True)
    port = models.PositiveIntegerField('Puerto SMTP', default=587,
                                       validators=[MinValueValidator(1), MaxValueValidator(65535)])
    connection_type = models.CharField('Tipo de conexión', max_length=12, choices=ConnectionType.choices, default=ConnectionType.AUTO,
                                       help_text='Automático: 587 STARTTLS, 465 TLS/SSL, 25 sin SSL/TLS. Para otro puerto, seleccione el tipo de conexión.')
    username = models.CharField('Usuario (casilla de notificaciones)', max_length=254, blank=True)
    password_ciphertext = models.TextField(editable=False, blank=True)
    from_email = models.EmailField('Correo remitente', blank=True)
    from_name = models.CharField('Nombre del remitente', max_length=120, default='Surgeon — Gestión de Pabellones')
    public_url = models.URLField('Dirección HTTPS de la aplicación', blank=True)
    notify_reminder = models.BooleanField('Recordatorio de asistencia al médico', default=True)
    reminder_minutes = models.PositiveIntegerField('Anticipación del recordatorio (minutos)', default=180,
        validators=[MinValueValidator(1), MaxValueValidator(1440)])
    notify_confirmed = models.BooleanField('Reserva confirmada', default=True)
    notify_modified = models.BooleanField('Reserva modificada', default=True)
    notify_cancelled = models.BooleanField('Reserva cancelada', default=True)
    notify_relocated = models.BooleanField('Reasignación automática', default=True)
    notify_reschedule = models.BooleanField('Pendiente de reprogramación', default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def resolved_connection_type(self):
        if self.connection_type not in self.ConnectionType.values:
            raise ValueError('Tipo de conexión SMTP no válido.')
        if self.connection_type != self.ConnectionType.AUTO:
            return self.connection_type
        modes = {587: self.ConnectionType.STARTTLS, 465: self.ConnectionType.TLS, 25: self.ConnectionType.PLAIN}
        if self.port not in modes:
            raise ValueError('Seleccione un tipo de conexión para este puerto no estándar.')
        return modes[self.port]

    def set_password(self, value):
        from .smtp_credentials import encrypt_password
        self.password_ciphertext = encrypt_password(value)

    def get_password(self):
        from .smtp_credentials import decrypt_password
        return decrypt_password(self.password_ciphertext)

    def clean(self):
        from urllib.parse import urlsplit
        super().clean()
        if self.connection_type == self.ConnectionType.AUTO and self.port not in (25, 465, 587):
            raise ValidationError({'connection_type': 'Para un puerto no estándar, seleccione explícitamente el tipo de conexión.'})
        if self.enabled:
            missing = {field: 'Complete este dato para activar los envíos.'
                       for field in ['host', 'username', 'from_email', 'public_url'] if not getattr(self, field)}
            if not self.password_ciphertext:
                missing['enabled'] = 'Ingrese una contraseña SMTP antes de activar los envíos.'
            if missing:
                raise ValidationError(missing)
        if self.host and any(char.isspace() for char in self.host) or '://' in self.host:
            raise ValidationError({'host': 'Ingrese solo el nombre del servidor, sin protocolo ni espacios.'})
        if self.public_url and (urlsplit(self.public_url).scheme != 'https' or urlsplit(self.public_url).query
                                or urlsplit(self.public_url).fragment or urlsplit(self.public_url).username):
            raise ValidationError({'public_url': 'Ingrese la dirección HTTPS de la aplicación, sin credenciales, parámetros ni fragmentos.'})

    class Meta:
        verbose_name = 'configuración de correo'
        verbose_name_plural = 'configuración de correo'
        constraints = [models.CheckConstraint(condition=Q(pk=1), name='single_email_settings'),
                       models.CheckConstraint(condition=Q(reminder_minutes__gte=1, reminder_minutes__lte=1440), name='valid_reminder_minutes')]

    def __str__(self):
        return 'Notificaciones por correo'


class EmailNotification(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendiente'
        SENT = 'sent', 'Enviada'
        FAILED = 'failed', 'Fallida'
        SKIPPED = 'skipped', 'Omitida'

    reservation = models.ForeignKey(Reservation, null=True, blank=True, related_name='email_notifications', on_delete=models.PROTECT)
    event = models.CharField('Aviso', max_length=24)
    dedupe_key = models.CharField(max_length=64, unique=True, editable=False)
    scheduled_start_at = models.DateTimeField('Inicio programado al crear el recordatorio', null=True, blank=True)
    recipient = models.EmailField('Destinatario')
    subject = models.CharField('Asunto', max_length=200)
    body = models.TextField('Mensaje')
    status = models.CharField('Estado', max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField('Intentos', default=0)
    next_attempt_at = models.DateTimeField('Próximo intento', default=timezone.now, db_index=True)
    last_error = models.CharField('Último error', max_length=200, blank=True)
    created_at = models.DateTimeField('Creada', auto_now_add=True)
    sent_at = models.DateTimeField('Enviada', null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'notificación por correo'
        verbose_name_plural = 'notificaciones por correo'
