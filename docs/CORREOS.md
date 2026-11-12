# Notificaciones por correo

## Configuración en Administración

Después de aplicar la migración 0020 y ejecutar `setup_roles`, un usuario del perfil Administrador con acceso al panel o un superusuario puede abrir **Configuración de correo** y crear la configuración única.

Configurar servidor SMTP, puerto (587 por defecto), usuario, contraseña, dirección y nombre del remitente, y dirección HTTPS de la aplicación. El transporte usa el tipo de conexión elegido: automático por puerto (587 STARTTLS, 465 TLS/SSL implícito, 25 sin SSL/TLS) o selección explícita de STARTTLS, TLS/SSL o sin cifrado. Para puertos no estándar se debe seleccionar el tipo explícitamente. STARTTLS y TLS verifican los certificados y no se degradan a una conexión sin cifrado si fallan. La dirección de la aplicación debe corresponder al sitio web, que puede tener un dominio diferente al correo remitente.

La contraseña se ingresa únicamente en Administración. Se almacena cifrada con Fernet y no se vuelve a precargar, mostrar ni registrar en los mensajes de error. Dejar el campo vacío conserva la contraseña; escribir otra la reemplaza. La clave de cifrado se deriva de `SMTP_CREDENTIAL_KEY` o, si está vacío, de `DJANGO_SECRET_KEY`. Todos los servicios deben compartir esa clave. Conservarla junto al respaldo de configuración: al cambiarla hay que volver a ingresar la contraseña SMTP. Las credenciales y claves no se guardan en GitHub.

Completar **Correo electrónico** de los médicos en **Médicos** y de las cuentas en **Usuarios**. Las cuentas de usuarios ya disponían de ese campo; ahora se muestra también en el listado y en el formulario de alta. Los médicos incorporan un campo nuevo. Ambos admiten campos vacíos para conservar cuentas existentes, pero sin dirección no recibirán mensajes.

Marcar **Activar notificaciones por correo** y los tipos de aviso deseados. El botón **Enviar prueba a mi correo** encola una prueba para la cuenta del administrador conectado. Ver su resultado en **Notificaciones por correo**. Esta prueba utiliza la configuración guardada; no guarda cambios pendientes del formulario.

La migración 0021 conserva STARTTLS explícito para las configuraciones existentes, sin cambiar sus credenciales. Al cambiar el puerto en Administración se sugiere automáticamente su tipo y se muestra junto al selector; se puede sobrescribir para configuraciones particulares.

## Destinatarios y avisos

Los destinatarios son el correo del cirujano de la reserva (o el de su cuenta activa vinculada si el primero está vacío), el usuario activo que la creó y los usuarios activos del grupo Administrador o superusuarios. Se omiten direcciones vacías/inválidas y se deduplican sin distinguir mayúsculas. Cada destinatario recibe un mensaje separado.

Se notifican confirmación, modificación manual, cancelación, reasignación automática por alargue y reserva sin tiempo útil pendiente de reprogramación. Los ajustes automáticos por salida del paciente generan modificación o pendiente de reprogramación, según corresponda. El mensaje incluye referencia de reserva, pabellón, horarios y enlace autenticado; no incluye nombre del paciente, RUT, diagnóstico ni operación. El motivo detallado de una cancelación se consulta dentro de la aplicación.

Solo se encolan eventos nuevos mientras las notificaciones y su tipo estén habilitados. No hay envío retroactivo de estos eventos en reservas anteriores. Los recordatorios de asistencia sí consideran las reservas próximas existentes; ver [Agenda del médico](AGENDA_MEDICO.md). Desactivar globalmente los correos pausa también la entrega de lo ya encolado; los interruptores de cada tipo afectan a los eventos nuevos.

## Entrega y recuperación

El servicio Compose **mail-delivery** procesa la cola cada 15 segundos, independientemente de la web y del monitor de alargues. Tiene salida de red para SMTP, sin publicar puertos. Los cambios de reserva y sus mensajes se guardan en la misma transacción, pero la conexión SMTP ocurre en otro proceso; una caída de SMTP no revierte la reserva.

Cada mensaje tiene una clave de deduplicación y Message-ID estable. PostgreSQL bloquea los pendientes para que dos procesos no envíen simultáneamente la misma fila. Ante errores, reintenta después de 1, 5, 15 y 60 minutos; al quinto fallo queda **Fallida**. Administración muestra estado, intentos y un diagnóstico sin respuestas SMTP ni credenciales. La acción **Reintentar notificaciones fallidas** vuelve a encolarlas después de corregir la configuración.

**Enviada** significa que el servidor SMTP aceptó el mensaje; no confirma la recepción en la bandeja final. Si SMTP acepta el mensaje y se pierde la respuesta o el proceso antes de guardar el resultado, un reintento podría repetirlo: SMTP no permite garantizar entrega exactamente una vez.

## Despliegue

Construir la misma revisión para `web`, `overrun-monitor` y `mail-delivery`; detenerlos, aplicar `migrate`, ejecutar `setup_roles` y arrancar los tres. No poner usuario ni contraseña SMTP en `.env`: se administran desde el panel. `SMTP_CREDENTIAL_KEY` es opcional y solo cifra las credenciales; no es la contraseña del correo.

Consultar errores: `docker compose logs --tail=50 mail-delivery`. Para procesar una pasada manual: `docker compose run --rm mail-delivery python manage.py send_notifications --once`.

Las pruebas automatizadas usan direcciones ficticias y transporte local simulado. La conexión real debe comprobarse desde la VM con el botón de prueba después de ingresar las credenciales.
