import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from theatre.email_delivery import deliver_pending
from theatre.reminders import queue_reminders


class Command(BaseCommand):
    help = 'Envía la cola de notificaciones SMTP con reintentos.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--interval', type=int, default=15)

    def handle(self, *args, **options):
        if not 5 <= options['interval'] <= 300:
            raise CommandError('El intervalo debe estar entre 5 y 300 segundos.')
        while True:
            if not options['once']:
                close_old_connections()
            try:
                queue_reminders()
                count = deliver_pending()
                if count or options['once']:
                    self.stdout.write(f'Notificaciones procesadas: {count}')
            except Exception:
                if options['once']:
                    raise
                # No incluir errores ni respuestas que puedan contener credenciales.
                self.stderr.write('No se pudo procesar la cola. Se reintentará en el siguiente ciclo.')
            finally:
                if not options['once']:
                    close_old_connections()
            if options['once']:
                return
            time.sleep(options['interval'])
