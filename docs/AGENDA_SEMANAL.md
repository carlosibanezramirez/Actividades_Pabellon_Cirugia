# Agenda semanal continua de un pabellón

Disponible desde **Agenda semanal** o `/agenda-semanal/`. Se elige un pabellón y una fecha; se muestran los siete días de la semana correspondiente, de lunes a domingo. Las flechas permiten cambiar de semana manteniendo el pabellón elegido.

Cada día es una banda continua: verde donde hay disponibilidad y rojo en los intervalos reservados u ocupados. No se redondean los intervalos a bloques de una hora. Un pabellón desactivado aparece no disponible y no admite reservas. Las reservas creadas en la agenda horaria anterior también bloquean su intervalo exacto en esta vista.

## Reservar un día

Al presionar un día se abre únicamente ese día, junto con su disponibilidad y el formulario:

- Médico solicitante.
- Nombre del paciente.
- RUT del paciente, con dígito verificador válido. Se normaliza al formato sin puntos y con guion.
- Tipo de cirugía.
- Inicio deseado, exclusivamente a la hora o media hora (`:00` o `:30`).
- Duración entera en minutos, de 1 a 1440 (hasta 24 horas).

La duración indicada por el médico abarca desde el inicio de preparación de anestesia hasta la salida del paciente. El sistema agrega **15 minutos previos de preparación del pabellón**.

Por ejemplo: inicio solicitado `09:30`, duración `90` minutos. El pabellón queda reservado de **09:15 a 11:00**. Se comprueba disponibilidad para los 105 minutos completos. Una duración de 20 minutos ocupa 35 minutos; no se redondea a una hora.

El comienzo de los 15 minutos previos no puede estar en el pasado. Se rechaza cualquier intersección con una reserva o uso ya registrado del mismo pabellón, aunque el conflicto solo afecte la preparación. Intervalos contiguos que se tocan exactamente sin superponerse sí se permiten.

La preparación puede comenzar el día anterior y la intervención puede terminar el siguiente; se comprueban y colorean todos los días afectados. Tras guardar se vuelve al día seleccionado con el tramo ocupado en rojo, un mensaje con el horario completo y la reserva en el listado.

Los horarios se guardan en UTC y se muestran en America/Santiago. En cambios de hora se usan duraciones reales; se rechazan horas de inicio inexistentes o ambiguas. La escala continua contempla días de 23 o 25 horas.

Cada reserva muestra dentro de su tramo rojo el tipo de cirugía, el médico y el horario reservado completo (incluidos los 15 minutos previos). Las reservas contiguas conservan textos separados. Al pasar el mouse, enfocar con teclado o tocar el bloque se muestra un recuadro con esos datos más el nombre y RUT del paciente. Escape o un toque fuera cierran el recuadro. En tramos cortos o columnas estrechas el texto interior puede recortarse; el recuadro conserva el detalle completo sin agrandar artificialmente el intervalo horario.

El RUT es obligatorio para las nuevas reservas en ambas agendas. Las reservas existentes sin RUT mantienen sus datos y muestran «No registrado»; la migración no les asigna un identificador ficticio. Estos detalles siguen protegidos por autenticación y permiso de acceso a las intervenciones.

## Convivencia con la agenda anterior

Las dos agendas comparten las mismas reservas y el mismo bloqueo transaccional por pabellón, evitando superposiciones entre solicitudes simultáneas de cualquiera de ellas. La agenda horaria anterior conserva sus bloques de al menos una hora; la nueva agenda usa minutos más los 15 minutos de preparación.

La disponibilidad continua considera el uso real sin imponerle el mínimo artificial de una hora de la vista anterior. Una intervención abierta sigue bloqueando el resto del día actual hasta que se registre su salida; no se proyecta indefinidamente sobre fechas futuras.

En el detalle de una nueva reserva se distingue el inicio de preparación del pabellón, el inicio solicitado por el médico y la duración estimada. Se conserva el enlace para iniciar la intervención desde esa reserva durante su horario, sin imponer una hora adicional a las reservas nuevas de menor duración. Los eventos clínicos se registran con sus horas reales, no se completan automáticamente a partir de la estimación.

## Actualización

La migración agrega `planned_start_at` y reemplaza la restricción anterior por una que admite los dos tipos de reserva. Conserva las reservas existentes con sus horarios y el mínimo de una hora de su modalidad original.

Crear un respaldo antes de instalar y aplicar las migraciones con el servicio web detenido. Una vez registradas reservas nuevas de menos de una hora, no revertir la migración a la restricción anterior sin un plan para esos datos; una reversión directa puede fallar. Los nombres de pacientes y datos reales permanecen únicamente en la base de la VM, nunca en el repositorio.
