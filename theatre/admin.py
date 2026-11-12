from django import forms
from django.contrib import admin, messages
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from .forms import ProfileUserChangeForm, ProfileUserCreationForm, EmailSettingsForm
from .models import CancellationReason, Correction, Doctor, Event, Intervention, OperatingSettings, Procedure, Reservation, Room, Specialty, PreoperativeActivity, ReservationAdjustment, AutomaticRelocation, EmailSettings, EmailNotification


@admin.register(OperatingSettings)
class OperatingSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ('Preparación del pabellón', {
            'fields': ['preparation_mean_minutes', 'preparation_max_minutes'],
            'description': 'La continuidad entre reservas mantiene un máximo de 30 minutos. Un tiempo medio mayor de 30 minutos impedirá encadenar reservas posteriores en el mismo día.',
        }),
    ]
    fieldsets.append(('Reasignación por alargue', {'fields': ['allowed_overrun_minutes']}))
    list_display = ['__str__', 'preparation_mean_minutes', 'preparation_max_minutes', 'allowed_overrun_minutes']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CancellationReason)
@admin.register(Procedure)
class CatalogAdmin(admin.ModelAdmin):
    list_display = ['name', 'active']
    list_filter = ['active']
    search_fields = ['name']


@admin.register(Room)
class RoomAdmin(CatalogAdmin):
    list_display = ['name', 'room_type', 'opening_time', 'closing_time', 'active']
    fields = ['name', 'room_type', 'active', 'opening_time', 'closing_time']
    list_filter = ['room_type', 'active']
    formfield_overrides = {models.TimeField: {'widget': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'step': 60})}}


@admin.register(Specialty)
class SpecialtyAdmin(CatalogAdmin):
    list_display = ['name', 'is_anesthesia', 'active']
    list_filter = ['active', 'is_anesthesia']


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class ProfileUserAdmin(UserAdmin):
    add_form = ProfileUserCreationForm
    form = ProfileUserChangeForm
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos personales', {'fields': ('first_name', 'last_name', 'email')}),
        ('Perfiles', {'fields': ('groups', 'is_staff')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    filter_horizontal = ('user_permissions',)


@admin.register(Doctor)
class DoctorAdmin(CatalogAdmin):
    list_display = ['name', 'specialty', 'email', 'active']
    list_filter = ['active', 'specialty']
    search_fields = ['name', 'email', 'specialty__name']
    list_select_related = ['specialty']

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'specialty' in form.base_fields:
            # Mantener visible la selección previa aunque se desactive del catálogo.
            choices = Q(active=True)
            if obj and obj.specialty_id:
                choices |= Q(pk=obj.specialty_id)
            form.base_fields['specialty'].queryset = Specialty.objects.filter(choices)
        return form


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PreoperativeActivity)
class PreoperativeActivityAdmin(ReadOnlyAdmin):
    list_display = ['intervention', 'kind', 'completed_at', 'completed_by']
    list_filter = ['kind']


@admin.register(Intervention)
class InterventionAdmin(ReadOnlyAdmin):
    list_display = ['id', 'room', 'procedure', 'doctor', 'anesthetist', 'created_at', 'completed_at']
    list_filter = ['room']


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = ['intervention', 'stage', 'occurred_at', 'original_at', 'recorded_by']


@admin.register(Correction)
class CorrectionAdmin(ReadOnlyAdmin):
    list_display = ['event', 'previous_at', 'new_at', 'reason', 'corrected_by', 'corrected_at']


@admin.register(AutomaticRelocation)
class AutomaticRelocationAdmin(ReadOnlyAdmin):
    list_display = ['reservation', 'source_intervention', 'from_room', 'to_room', 'starts_at', 'ends_at', 'recorded_at']


@admin.register(ReservationAdjustment)
class ReservationAdjustmentAdmin(ReadOnlyAdmin):
    list_display = ['reservation', 'source_intervention', 'previous_start', 'previous_end', 'new_start', 'new_end', 'recorded_by']


@admin.register(Reservation)
class ReservationAdmin(ReadOnlyAdmin):
    list_display = ['id', 'room', 'starts_at', 'ends_at', 'doctor', 'procedure', 'patient_name', 'created_by', 'cancelled_at', 'cancellation_reason_name', 'cancelled_by']
    list_filter = ['room', 'doctor']
    search_fields = ['patient_name', 'patient_rut', 'doctor__name']


@admin.register(EmailSettings)
class EmailSettingsAdmin(admin.ModelAdmin):
    form = EmailSettingsForm
    change_form_template = 'admin/theatre/emailsettings/change_form.html'
    fieldsets = [
        ('Conexión con el servicio de correos', {'fields': ['enabled', 'host', 'port', 'connection_type', 'username', 'smtp_password', 'password_saved']}),
        ('Remitente y aplicación', {'fields': ['from_email', 'from_name', 'public_url']}),
        ('Avisos habilitados', {'fields': ['notify_confirmed', 'notify_modified', 'notify_cancelled',
                                          'notify_relocated', 'notify_reschedule']}),
    ]
    readonly_fields = ['password_saved']

    class Media:
        js = ('admin-smtp-connection.js',)

    @method_decorator(sensitive_post_parameters('smtp_password', 'username'))
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)

    @admin.display(description='Contraseña almacenada', boolean=True)
    def password_saved(self, obj):
        return bool(obj and obj.password_ciphertext)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not EmailSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path('prueba/', self.admin_site.admin_view(self.send_test), name='theatre_emailsettings_test')] + super().get_urls()

    def send_test(self, request):
        if request.method != 'POST':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['POST'])
        if not self.has_change_permission(request):
            raise PermissionDenied
        from .notifications import queue_test_email
        config = EmailSettings.objects.filter(pk=1, enabled=True).first()
        if config is None:
            messages.error(request, 'Guarde y active la configuración antes de enviar una prueba.')
        elif not request.user.email:
            messages.error(request, 'Ingrese su correo en su cuenta de usuario antes de enviar una prueba.')
        else:
            from django.core.exceptions import ValidationError
            try:
                queue_test_email(config, request.user.email)
            except ValidationError:
                messages.error(request, 'Su cuenta debe tener una dirección de correo válida.')
                return redirect(reverse('admin:theatre_emailsettings_changelist'))
            messages.success(request, 'Prueba encolada para su correo. Consulte Notificaciones por correo para ver el resultado.')
        return redirect(reverse('admin:theatre_emailsettings_changelist'))


@admin.register(EmailNotification)
class EmailNotificationAdmin(ReadOnlyAdmin):
    list_display = ['created_at', 'reservation', 'event', 'recipient', 'status', 'attempts', 'sent_at']
    list_filter = ['status', 'event']
    search_fields = ['recipient']
    exclude = ['dedupe_key']
    actions = ['retry_failed']

    @admin.action(description='Reintentar notificaciones fallidas', permissions=['retry'])
    def has_retry_permission(self, request):
        return request.user.has_perm('theatre.change_emailsettings')

    def retry_failed(self, request, queryset):
        if not request.user.has_perm('theatre.change_emailsettings'):
            raise PermissionDenied
        count = queryset.filter(status='failed').update(status='pending', attempts=0, next_attempt_at=timezone.now(), last_error='')
        self.message_user(request, f'Notificaciones reencoladas: {count}')
