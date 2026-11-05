import unicodedata
from django.db import migrations


def mark_anesthesia(apps, schema_editor):
    Specialty = apps.get_model('theatre', 'Specialty')
    database = schema_editor.connection.alias
    names = {'anestesia', 'anestesista', 'anestesiologia', 'anestesiologo',
             'anestesia (anestesista)', 'anestesiologia y reanimacion'}
    found = False
    for specialty in Specialty.objects.using(database).all().iterator():
        normalized = ''.join(
            char for char in unicodedata.normalize('NFKD', specialty.name.strip().casefold())
            if not unicodedata.combining(char)
        )
        if normalized in names:
            specialty.is_anesthesia = True
            specialty.save(using=database, update_fields=['is_anesthesia'])
            found = True
    if not found:
        Specialty.objects.using(database).get_or_create(
            name='Anestesia', defaults={'is_anesthesia': True},
        )


class Migration(migrations.Migration):
    dependencies = [('theatre', '0004_intervention_anesthetist_specialty_is_anesthesia')]
    operations = [migrations.RunPython(mark_anesthesia, migrations.RunPython.noop)]
