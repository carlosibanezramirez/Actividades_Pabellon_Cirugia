from django.db import migrations, models
import django.db.models.deletion


def copy_specialties(apps, schema_editor):
    Doctor = apps.get_model('theatre', 'Doctor')
    Specialty = apps.get_model('theatre', 'Specialty')
    database = schema_editor.connection.alias
    for doctor in Doctor.objects.using(database).exclude(specialty='').iterator():
        name = doctor.specialty.strip()
        if name:
            specialty, _ = Specialty.objects.using(database).get_or_create(name=name)
            doctor.specialty_selection_id = specialty.pk
            doctor.save(using=database, update_fields=['specialty_selection'])


def restore_text(apps, schema_editor):
    Doctor = apps.get_model('theatre', 'Doctor')
    database = schema_editor.connection.alias
    for doctor in Doctor.objects.using(database).select_related('specialty_selection').iterator():
        doctor.specialty = doctor.specialty_selection.name if doctor.specialty_selection_id else ''
        doctor.save(using=database, update_fields=['specialty'])


class Migration(migrations.Migration):
    dependencies = [('theatre', '0002_doctor_specialty')]

    operations = [
        migrations.CreateModel(
            name='Specialty',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160, unique=True, verbose_name='Nombre')),
                ('active', models.BooleanField(default=True, verbose_name='Activo')),
            ],
            options={'verbose_name': 'especialidad', 'verbose_name_plural': 'especialidades', 'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='doctor', name='specialty_selection',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='theatre.specialty', verbose_name='Especialidad'),
        ),
        migrations.RunPython(copy_specialties, restore_text),
        migrations.RemoveField(model_name='doctor', name='specialty'),
        migrations.RenameField(model_name='doctor', old_name='specialty_selection', new_name='specialty'),
    ]
