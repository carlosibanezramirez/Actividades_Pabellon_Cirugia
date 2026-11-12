# Agenda personal del médico

Aplicar las migraciones hasta 0022 y ejecutar `python manage.py setup_roles`.

En Administración, crear una cuenta de usuario con contraseña y correo electrónico. En **Médicos**, vincularla mediante **Cuenta de acceso del médico**. El vínculo asigna automáticamente el perfil **Médico**; al desvincularla se retira ese perfil. Una cuenta solo puede estar vinculada a un médico. Para acceso limitado a su agenda, no agregar perfiles Operador o Administrador: los permisos de perfiles se acumulan.

Al iniciar sesión, el médico activo vinculado entra en **Mi agenda**. Puede cambiar de semana y consultar sus reservas, pacientes, pabellones, estados y eventos registrados. La vista es de consulta; no permite modificar reservas ni registrar eventos. Se incluyen las intervenciones de las que es cirujano responsable, también las creadas sin reserva. Las reservas canceladas y pendientes de reprogramación conservan su estado visible. Los enlaces comprueban la propiedad en el servidor.

## Recordatorios

En **Configuración de correo**, habilitar los correos y **Recordatorio de asistencia**. El margen predeterminado es 180 minutos y puede cambiarse entre 1 y 1440 minutos. El servicio existente `mail-delivery` revisa cada 15 segundos las reservas próximas: usa el inicio solicitado de la intervención, sin sumar la preparación previa del pabellón. Una reserva creada dentro del margen recibe el aviso en la siguiente pasada.

El destinatario es únicamente el médico: primero se utiliza su correo en Médicos y, si está vacío, el de su cuenta activa vinculada. No se envían estos recordatorios a administradores ni al creador de la reserva. No incluyen paciente, RUT, diagnóstico ni operación; el enlace exige iniciar sesión.

Cada reserva, horario y destinatario tiene un único recordatorio en la cola. Antes de enviarlo se comprueba nuevamente su vigencia: se omite si fue cancelada, quedó pendiente de reprogramación, cambió su inicio o destinatario, venció o ya comenzó la preparación de anestesia. Una reasignación de pabellón conservando el horario actualiza el lugar en el mensaje pendiente. La preparación de pabellón y los consentimientos previos no impiden el recordatorio.

El mecanismo también considera reservas existentes que aún están dentro del margen. SMTP conserva sus reintentos habituales; una interrupción puede retrasar el envío. El estado Enviada indica aceptación por el servidor SMTP.

## Canales futuros

SMS requerirá un proveedor con API, sus credenciales, remitente habilitado y teléfonos de médicos con código de país (formato E.164).

WhatsApp requerirá una cuenta empresarial y número habilitado, acceso a WhatsApp Business Platform/Cloud API o un proveedor, credenciales, una plantilla de recordatorio aprobada y autorización de los destinatarios. Estos canales todavía no están implementados. Las credenciales deberán administrarse fuera de GitHub.
