from django import forms
from .models import Doctor, Intervention, Procedure, Room


class InterventionForm(forms.ModelForm):
    class Meta:
        model = Intervention
        fields = ['room', 'procedure', 'doctor']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, model in [('room', Room), ('procedure', Procedure), ('doctor', Doctor)]:
            self.fields[field].queryset = model.objects.filter(active=True)


class CorrectionForm(forms.Form):
    new_at = forms.DateTimeField(
        label='Nueva fecha y hora (Chile)',
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M:%S', attrs={'type': 'datetime-local', 'step': '1'}),
        input_formats=['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'],
        help_text='Horario America/Santiago. Se rechazará una hora ambigua durante un cambio de horario.',
    )
    reason = forms.CharField(label='Motivo de la corrección', max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))
    expected_at = forms.DateTimeField(widget=forms.HiddenInput)
