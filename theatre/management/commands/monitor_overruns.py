import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from theatre.overruns import process_overruns

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reasigna la siguiente reserva al superar el alargue permitido, sin enviar correos.'

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
                count = process_overruns()
                if count or options['once']:
                    self.stdout.write(f'Reasignaciones realizadas: {count}')
            except Exception:
                if options['once']:
                    raise
                logger.exception('No se pudo comprobar el alargue; se reintentará en el siguiente ciclo.')
            finally:
                if not options['once']:
                    close_old_connections()
            if options['once']:
                return
            time.sleep(options['interval'])
