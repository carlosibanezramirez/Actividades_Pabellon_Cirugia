from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Crea o actualiza los perfiles Operador y Administrador sin crear usuarios ni contraseñas.'

    def handle(self, *args, **options):
        operate = Permission.objects.get(content_type__app_label='theatre', codename='operate_intervention')
        correct = Permission.objects.get(content_type__app_label='theatre', codename='correct_event')
        operator, _ = Group.objects.get_or_create(name='Operador')
        operator.permissions.set([operate])
        administrator, _ = Group.objects.get_or_create(name='Administrador')
        catalog = Permission.objects.filter(content_type__app_label='theatre', content_type__model__in=['room', 'procedure', 'doctor', 'specialty'])
        administrator.permissions.set([operate, correct, *catalog])
        self.stdout.write(self.style.SUCCESS('Perfiles preparados. Asigne los usuarios desde Administración.'))
