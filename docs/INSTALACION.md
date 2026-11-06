# Instalación en una VM Ubuntu

El repositorio contiene el código. La aplicación se ejecuta en la VM mediante Docker Compose; GitHub no aloja la aplicación. Las direcciones y credenciales reales se configuran exclusivamente en `.env` dentro de la VM.

## Requisitos

- Ubuntu 26.04 con acceso administrativo, Git, Docker Engine y el complemento Docker Compose instalados siguiendo la documentación oficial de Docker para la versión del sistema. Comprobar disponibilidad y compatibilidad del proveedor antes de instalar.
- El dominio debe resolver a la dirección pública del servidor; revisar también cualquier registro AAAA existente.
- Puertos TCP 80 y 443 disponibles para Caddy y la emisión del certificado. Acceso SSH limitado a la red de administración.
- Reloj sincronizado con NTP. Los registros se guardan en UTC y se muestran en America/Santiago.
- No publicar puertos de PostgreSQL ni del contenedor web. El acceso web pasa por Caddy.

## Primera instalación

Usar una cuenta autorizada de la VM. El directorio `/opt/pabellon` debe estar creado y asignado a esa cuenta por el administrador.

```bash
git clone https://github.com/carlosibanezramirez/Actividades_Pabellon_Cirugia.git /opt/pabellon
cd /opt/pabellon
git switch feature/base-aplicacion
cp .env.example .env
chmod 600 .env
```

La rama inicial sirve para validación. Para uso operativo, elegir posteriormente una etiqueta revisada desde `main`; no seguir automáticamente una rama de desarrollo.

Editar `.env` localmente: dominio real, correo del responsable del certificado y dos secretos independientes. Generar cada secreto con `openssl rand -hex 32`. No reutilizar los valores de ejemplo. No compartir la salida ni subir el archivo a GitHub.

```bash
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate --noinput
docker compose run --rm web python manage.py setup_roles
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm web python manage.py check --deploy --fail-level WARNING
docker compose up -d
docker compose ps
docker compose logs --tail=100 web caddy
```

Las migraciones se ejecutan como tarea explícita antes de iniciar el servicio, no en cada proceso Gunicorn. Caddy obtiene y renueva el certificado HTTPS. Verificar el sitio desde un navegador y revisar los registros si el certificado no se emite.

## Configuración inicial

1. Entrar a `/admin/` con el superusuario.
2. Configurar pabellones, tipos de operación y médicos. No se cargan listas ficticias automáticamente.
3. Crear cuentas individuales y seleccionar uno o más **Perfiles** desde el mismo formulario de creación. Los perfiles disponibles corresponden a los grupos (inicialmente **Operador** y **Administrador**) y sus permisos se acumulan. También se pueden modificar al editar el usuario; se exige al menos un perfil en estos formularios.
4. Para administrar listas desde `/admin/`, el usuario del grupo Administrador debe tener además habilitado `staff`. Ese grupo no concede gestión de cuentas; el superusuario gestiona usuarios y contraseñas.
5. Operadores pueden registrar y consultar todas las intervenciones de esta instalación. Administradores pueden corregir horarios con motivo obligatorio. No hay segregación por establecimiento en esta versión.
6. Cada pabellón puede tener una sola intervención abierta. Al registrar la salida del paciente queda disponible para otra.
7. En **Especialidades**, marcar **Habilita como anestesista** para las especialidades de anestesia. La actualización reconoce los nombres habituales ya existentes (Anestesia, Anestesista y Anestesiología, entre otros); si no encuentra ninguno, crea la opción Anestesia. Para otros nombres, revisar y activar la marca manualmente.
8. Asignar a cada anestesista su especialidad desde **Médicos**. Al crear una intervención, el campo **Anestesista** es obligatorio y muestra únicamente médicos activos con especialidad activa habilitada para anestesia. El servidor también comprueba esta condición al guardar. Las intervenciones anteriores conservan sus datos y muestran «No registrado (intervención anterior)» si no tenían anestesista.

Verificar una intervención ficticia completa, el rechazo de un salto de etapa, la consulta posterior y una corrección auditada antes de usar el sistema con actividad real. Los botones guardan el momento de la pulsación; no se ingresan horas manualmente durante el registro normal.

## Respaldos y restauración

El volumen persistente no reemplaza un respaldo. Crear respaldos periódicos, cifrarlos y copiarlos fuera de la VM con acceso restringido. Nunca subirlos al repositorio. Definir retención y probar restauraciones antes de operar.

```bash
mkdir -p backups
chmod 700 backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/respaldo.dump
chmod 600 backups/respaldo.dump
```

Usar nombres fechados diferentes para conservar versiones. Respaldar también `.env` por un canal seguro separado y los datos de Caddy si se desea conservar su estado.

Para restaurar: validar el archivo primero en un entorno aislado. La orden siguiente reemplaza datos de la base destino; detener el servicio web y usarla únicamente con un respaldo elegido y confirmado por el administrador.

```bash
docker compose stop web
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' < backups/respaldo.dump
docker compose up -d web
```

## Actualizaciones

Revisar el pull request, esperar CI y etiquetar la entrega antes de desplegar. Crear y verificar un respaldo; detener el servicio web durante la actualización, obtener la etiqueta elegida con Git, reconstruir la imagen, ejecutar migraciones y reiniciar. Verificar acceso, registros anteriores y el flujo en el navegador.

No automatizar el despliegue directo desde cada push. Si una migración modifica datos, volver a una imagen anterior puede ser insuficiente: planificar restauración y compatibilidad de la base antes de actualizar.

## Límites de esta primera versión

- Las reservas incluyen nombre del paciente; no existe ficha clínica ni integración con sistemas hospitalarios. Tampoco se incluye recuperación de contraseña por correo ni cancelación de intervenciones.
- Las correcciones cambian horarios de eventos existentes; no borran ni omiten etapas. Los eventos y auditorías son de solo lectura en el panel administrativo. Quien administre directamente la base puede alterar datos; la auditoría no es un registro externo inviolable.
- Una intervención abierta creada por error requiere revisión administrativa; no se proporciona un botón para eliminarla.
- Configurar monitoreo de disponibilidad, almacenamiento, respaldos y reloj según la operación del servidor.
