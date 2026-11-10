from datetime import timedelta
from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from .models import CancellationReason, Doctor, Intervention, Procedure, Reservation, Room
from .rut import normalize_rut


class RutField(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(label='RUT del paciente', max_length=16,
                         help_text='Con dígito verificador; puede ingresarse con o sin puntos.', **kwargs)

    def clean(self, value):
        return normalize_rut(super().clean(value))


def profile_field():
    return forms.ModelMultipleChoiceField(
        label='Perfiles', queryset=Group.objects.order_by('name'),
        widget=forms.CheckboxSelectMultiple, required=True,
        help_text='Selecciona uno o más perfiles. Sus permisos se acumulan.',
    )


class ProfileUserCreationForm(AdminUserCreationForm):
    groups = profile_field()


class ProfileUserChangeForm(UserChangeForm):
    groups = profile_field()


def eligible_anesthetists():
    return Doctor.objects.filter(
        active=True, specialty__active=True, specialty__is_anesthesia=True,
    ).select_related('specialty')


class InterventionForm(forms.ModelForm):
    class Meta:
        model = Intervention
        fields = ['room', 'procedure', 'doctor', 'anesthetist', 'reservation']
        widgets = {'reservation': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, model in [('room', Room), ('procedure', Procedure), ('doctor', Doctor)]:
            self.fields[field].queryset = model.objects.filter(active=True)
        self.fields['anesthetist'].queryset = eligible_anesthetists()
        self.fields['anesthetist'].help_text = (
            'Solo médicos activos con especialidad activa habilitada para anestesia. '
            'Si falta un médico, solicita al administrador que revise su especialidad.'
        )


class CorrectionForm(forms.Form):
    new_at = forms.DateTimeField(
        label='Nueva fecha y hora (Chile)',
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M:%S', attrs={'type': 'datetime-local', 'step': '1'}),
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        help_text='Horario America/Santiago. Se rechazará una hora ambigua durante un cambio de horario.',
    )
    reason = forms.CharField(label='Motivo de la corrección', max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    expected_at = forms.DateTimeField(widget=forms.HiddenInput)


class DashboardFilterForm(forms.Form):
    desde = forms.DateField(label='Desde', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hasta = forms.DateField(label='Hasta', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('desde'), cleaned.get('hasta')
        if start and end and start > end:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la fecha inicial.')
        if end and end.year >= 9999:
            self.add_error('hasta', 'Seleccione una fecha anterior al año 9999.')
        return cleaned


class AgendaDateForm(forms.Form):
    fecha = forms.DateField(label='Fecha', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def clean_fecha(self):
        day = self.cleaned_data['fecha']
        if not 1900 <= day.year <= 9998:
            raise forms.ValidationError('Seleccione una fecha entre los años 1900 y 9998.')
        return day


class ReservationRequestForm(forms.Form):
    slots = forms.MultipleChoiceField(label='Horas seleccionadas', choices=[], required=True)
    doctor = forms.ModelChoiceField(label='Médico solicitante', queryset=Doctor.objects.filter(active=True))
    procedure = forms.ModelChoiceField(label='Tipo de cirugía', queryset=Procedure.objects.filter(active=True))
    patient_name = forms.CharField(label='Nombre del paciente', max_length=180)
    patient_rut = RutField()

    def __init__(self, *args, day=None, **kwargs):
        super().__init__(*args, **kwargs)
        if day:
            from .scheduling import day_slots
            slots = day_slots(day)
            self.fields['slots'].choices = [
                (f'{room_id}:{slot["index"]}', slot['label'])
                for room_id in Room.objects.values_list('pk', flat=True)
                for slot in slots
            ]


class WeeklySummaryForm(AgendaDateForm):

    def clean_fecha(self):
        day = super().clean_fecha()
        monday = day - timedelta(days=day.weekday())
        if monday.year < 1900 or (monday + timedelta(days=6)).year > 9997:
            raise forms.ValidationError('Seleccione una semana completa entre los años 1900 y 9997.')
        return day


class WeeklyAgendaForm(WeeklySummaryForm):
    room = forms.ModelChoiceField(label='Pabellón', queryset=Room.objects.all())


class ContinuousReservationForm(forms.Form):
    def __init__(self, *args, allowed_times=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_times = allowed_times
        if allowed_times is not None:
            self.fields['desired_time'].widget.choices = [('', 'Seleccione hora de inicio')] + [
                (value, value) for value in allowed_times
            ]

    doctor = forms.ModelChoiceField(label='Médico solicitante', queryset=Doctor.objects.filter(active=True))
    patient_name = forms.CharField(label='Nombre del paciente', max_length=180)
    patient_rut = RutField()
    procedure = forms.ModelChoiceField(label='Tipo de cirugía', queryset=Procedure.objects.filter(active=True))
    desired_time = forms.TimeField(
        label='Inicio deseado (preparación de anestesia)', input_formats=['%H:%M'],
        widget=forms.Select(choices=[('', 'Seleccione hora de inicio')] + [
            (f'{hour:02d}:{minute:02d}', f'{hour:02d}:{minute:02d}')
            for hour in range(24) for minute in [0, 30]
        ]),
    )
    duration_minutes = forms.IntegerField(
        label='Duración hasta la salida del paciente (minutos)', min_value=1, max_value=1440,
        help_text='Incluye preparación de anestesia, anestesia, cirugía y salida. Máximo 24 horas.',
    )

    def clean_desired_time(self):
        value = self.cleaned_data['desired_time']
        if value.minute not in (0, 30) or value.second or value.microsecond:
            raise forms.ValidationError('Seleccione un inicio a la hora o media hora.')
        if self.allowed_times is not None and value.strftime('%H:%M') not in self.allowed_times:
            raise forms.ValidationError('Seleccione un horario disponible que respete el máximo de 30 minutos desde el procedimiento anterior.')
        return value


class RescheduleReservationForm(AgendaDateForm):
    room = forms.ModelChoiceField(label='Pabellón', queryset=Room.objects.filter(active=True))
    desired_time = forms.TimeField(
        label='Hora de inicio', input_formats=['%H:%M'],
        widget=forms.Select(choices=[(f'{h:02d}:{m:02d}', f'{h:02d}:{m:02d}')
                                     for h in range(24) for m in [0, 30]]),
    )
    revision = forms.CharField(widget=forms.HiddenInput)

    def clean_fecha(self):
        day = super().clean_fecha()
        if day.year > 9997:
            raise forms.ValidationError('Seleccione una fecha hasta el año 9997.')
        return day


class CancelReservationForm(forms.Form):
    reason = forms.ModelChoiceField(label='Motivo de cancelación', queryset=CancellationReason.objects.filter(active=True))
    revision = forms.CharField(widget=forms.HiddenInput)
