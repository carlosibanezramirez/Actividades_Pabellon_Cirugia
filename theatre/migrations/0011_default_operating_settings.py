from django.db import migrations


def create_defaults(apps, schema_editor):
    apps.get_model('theatre', 'OperatingSettings').objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [('theatre', '0010_operatingsettings_and_more')]
    operations = [migrations.RunPython(create_defaults, migrations.RunPython.noop)]
