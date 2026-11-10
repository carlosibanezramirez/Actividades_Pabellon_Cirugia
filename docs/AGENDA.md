# Disponibilidad y reservas por fecha

Acceso desde **Agenda y reservas** o `/agenda/`. Requiere autenticación y permiso para operar intervenciones. La fecha se consulta mediante calendario y se muestran todos los pabellones y sus horas; se asume atención las 24 horas porque no hay un horario institucional configurado.

## Tarjetas de una hora

- **Verde:** libre.
- **Negro:** el bloque coincide con preparación real del pabellón.
- **Rojo:** el bloque coincide con un procedimiento o con el uso mínimo de una hora.
- **Café:** pabellón desactivado, reserva existente o intervención pendiente de preparación.

Una hora que toca cualquier reserva o intervalo ocupado queda bloqueada por completo. Si en una hora coinciden preparación y procedimiento, se muestra rojo; el catálogo desactivado tiene prioridad café. Las horas pasadas pueden consultarse, pero no reservarse.

El uso real comienza con el inicio de preparación (evento 1), o con la creación de la intervención cuando aún no se registra ese evento. Termina con la salida del paciente (evento 9). A efectos de disponibilidad, se considera al menos una hora desde el inicio, aunque la salida se registre antes. La preparación está incluida; no se agrega una hora adicional por separado.

Sin salida registrada, una intervención bloquea el resto del día actual y los días previos que siguió abierta. No se proyecta automáticamente sobre todos los días futuros: la disponibilidad futura representa programación y deberá revisarse si el uso real se prolonga. Las reservas de horarios fijos permanecen ocupadas durante todo su intervalo aun si una intervención termina anticipadamente.

## Crear una reserva

1. Elegir fecha y consultar.
2. Marcar una o más tarjetas verdes consecutivas del mismo pabellón. Al elegir otro pabellón, la selección anterior se limpia.
3. Seleccionar médico solicitante y tipo de cirugía de las listas activas.
4. Escribir el nombre y RUT del paciente (con dígito verificador válido) y confirmar.

Se registra pabellón, fecha y horas exactas, médico, cirugía, paciente, usuario y momento de creación. Una reserva dura como mínimo una hora y solo puede usar bloques completos que no hayan comenzado. Puede terminar a medianoche del día siguiente si se selecciona la última hora del día.

El servidor rechaza selecciones separadas, de diferentes pabellones, duplicadas o ya ocupadas. Un bloqueo transaccional por pabellón serializa las solicitudes simultáneas de reserva y de inicio de intervención. Las reservas se crean por este flujo; el panel administrativo solo permite consultarlas para no omitir estas validaciones.

Para mantener la continuidad, el comienzo de una nueva reserva horaria no puede quedar más de 30 minutos después del término de la reserva anterior de ese pabellón en el mismo día. La primera reserva del día puede elegir horario sin depender de días anteriores. La agenda semanal aplica el mismo límite al inicio solicitado por el médico y comprueba además sus 15 minutos previos de preparación.

Los horarios se almacenan en UTC y se muestran en America/Santiago. Los días de cambio de hora pueden tener 23 o 25 bloques; la agenda muestra el desplazamiento UTC cuando corresponde, para distinguir horas repetidas. Cada bloque representa una hora real.

## Consultar e iniciar

Las reservas del día aparecen debajo de la agenda. El detalle conserva el nombre del paciente, horarios y usuario que la registró. Solo usuarios con permiso pueden consultar estos datos.

Durante el horario reservado, **Crear intervención desde esta reserva** precarga pabellón, médico y operación. Se debe elegir además el anestesista. El servidor exige que esos datos coincidan con la reserva y permite vincular una sola intervención a ella.

Crear una intervención sin reserva se rechaza si coincide con una reserva durante la próxima hora mínima de uso. Iniciar una intervención reservada también se rechaza si esa hora mínima invade una reserva diferente. El registro clínico de eventos no se detiene por un sobretiempo: la agenda muestra la ocupación real y las reservas planificadas permanecen consultables.

Esta entrega registra y consulta reservas; no incluye cambios ni cancelaciones de reservas. La disponibilidad se recalcula al consultar y se vuelve a validar al confirmar; la selección local de tarjetas no aparta horas hasta guardar.
