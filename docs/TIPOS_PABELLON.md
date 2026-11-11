# Tipos de pabellón

En **Administración → Pabellones**, el campo **Tipo de pabellón** permite elegir:

- Pabellón Urgencias.
- Pabellón Cirugías Mayores.
- Pabellón Cirugías Menores.

Los pabellones existentes y nuevos tienen inicialmente el tipo Cirugías Mayores. Revisar y clasificar los existentes después de aplicar la migración 0015. Sus reservas y registros se conservan.

Urgencias nunca participa en la búsqueda/asignación automática de Nueva reserva, incluso para administradores. El guardado automático también verifica el tipo bajo bloqueo, por si cambió después de buscar.

Solo usuarios activos del perfil **Administrador** o superusuarios pueden generar reservas manuales en Urgencias, desde la agenda semanal/día o la agenda horaria. La condición de staff por sí sola no concede esta facultad. La misma restricción protege los traslados hacia o desde Urgencias. Las validaciones se realizan en el servidor; los operadores no reciben controles habilitados para reservar estos pabellones.

Los registros de actividad de urgencia y las cancelaciones mantienen sus permisos existentes. Los otros dos tipos conservan las reglas habituales de reserva.
