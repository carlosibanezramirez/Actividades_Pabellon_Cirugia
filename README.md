# Actividades del Pabellón de Cirugía

Aplicación para registrar actividades de una intervención quirúrgica con secuencia obligatoria y trazabilidad.

## Estado

Primera implementación disponible para validación en la rama `feature/base-aplicacion`. Incluye autenticación, listas administrables, registro secuencial y correcciones auditadas. No se ha desplegado en la VM.

## Instalación y pruebas

El [panel de control](docs/PANEL.md) está disponible en `/panel/`, con estados actuales de pabellones, detalle por estado y estadísticas de tiempos entre fechas de calendario.

El [tablero de pabellones](docs/TABLERO.md), en `/pabellones/`, muestra tarjetas con marquesinas de color, operación, médico responsable, horarios de uso y la última intervención finalizada.

Consultar [la guía de instalación](docs/INSTALACION.md) para configurar la VM, HTTPS, usuarios y respaldos. La configuración real se mantiene fuera de GitHub.

Con Python 3.12, un entorno virtual y PostgreSQL disponibles:

```bash
pip install -r requirements.txt
# Configurar POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
# POSTGRES_USER y POSTGRES_PASSWORD en el entorno local.
python manage.py test --settings=config.test_settings
```

Usar una base de pruebas aislada: Django crea y elimina una base con prefijo `test_`. El usuario de pruebas necesita permiso para crear bases. No usar credenciales de producción.

La comprobación rápida `TEST_SQLITE=1 python manage.py test --settings=config.test_settings` omite las pruebas de concurrencia. La integración continua usa PostgreSQL real para ejecutar la suite completa.

## Tecnología

Django y PostgreSQL. El código y sus ramas se mantienen en GitHub. El despliegue se realiza en una VM administrada por el propietario, independiente del alojamiento del repositorio.

## Requisitos

- Acceso con usuario y contraseña; asignación de uno o más perfiles al crear o editar usuarios.
- Selección de pabellón, tipo de operación, médico principal y anestesista desde listas configurables. El anestesista es obligatorio en las nuevas intervenciones y debe tener una especialidad activa habilitada para anestesia.
- Registro de fecha, hora y usuario responsable de cada evento.
- Persistencia para retomar intervenciones en curso y consultar sus duraciones.
- Correcciones administrativas con motivo obligatorio y auditoría del valor original, valor nuevo, autor y momento del cambio.

## Secuencia de eventos

1. Inicio de preparación del pabellón.
2. Término de preparación del pabellón.
3. Inicio de preparación de la anestesia.
4. Término de preparación de la anestesia.
5. Inicio del procedimiento de anestesia.
6. Inicio de la cirugía.
7. Término de la cirugía.
8. Término del proceso de anestesia.
9. Salida del paciente del pabellón.

Solo estará habilitado el siguiente evento pendiente. El servidor debe impedir saltos y duplicados, incluso ante solicitudes concurrentes. Las correcciones deben conservar el orden temporal.

## Ramas y entregas

- `main`: base estable; desplegar únicamente entregas validadas.
- `develop`: integración de funcionalidades.
- `feature/<nombre>`: desarrollo de funcionalidades.
- `fix/<nombre>`: correcciones.

Los cambios se integran mediante pull requests con descripción y verificaciones. Las entregas validadas se etiquetan con versiones como `v0.1.0`. Estas convenciones no constituyen reglas de protección automáticas de GitHub.

## Datos y configuración

No almacenar secretos, archivos `.env`, datos clínicos, bases de datos ni respaldos en GitHub. Los ejemplos de configuración no deben incluir credenciales ni detalles de infraestructura. Las pruebas deben usar datos ficticios.
