# Actividades del Pabellón de Cirugía

Aplicación para registrar actividades de una intervención quirúrgica con secuencia obligatoria y trazabilidad.

## Estado

Especificaciones iniciales. La implementación está pendiente; todavía no existe una versión desplegable.

## Tecnología

Django y PostgreSQL. El código y sus ramas se mantienen en GitHub. El despliegue se realiza en una VM administrada por el propietario, independiente del alojamiento del repositorio.

## Requisitos

- Acceso con usuario y contraseña; perfiles operador y administrador.
- Selección de pabellón, tipo de operación y médico principal desde listas configurables.
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
