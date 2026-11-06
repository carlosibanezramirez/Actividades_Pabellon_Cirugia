from django import forms
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group
from .models import Doctor, Intervention, Procedure, Room


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
        fields = ['room', 'procedure', 'doctor', 'anesthetist']

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
