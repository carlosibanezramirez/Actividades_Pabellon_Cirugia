# Agenda semanal continua de un pabellón

Disponible desde **Agenda semanal** o `/agenda-semanal/`. Se elige un pabellón y una fecha; se muestran los siete días de la semana correspondiente, de lunes a domingo. Las flechas permiten cambiar de semana manteniendo el pabellón elegido.

Las 24 horas siguen visibles: las franjas libres anteriores a la apertura y posteriores al cierre aparecen en celeste pálido y no admiten reservas. El horario predeterminado es 07:00–23:00 y la primera preparación puede comenzar antes de las 07:00. [Ver configuración y alarmas](CONFIGURACION.md).

Cada día es una banda continua: verde donde hay disponibilidad, negro en los 15 minutos previos de preparación y rojo en la intervención reservada u ocupada. No se redondean los intervalos a bloques de una hora. Un pabellón desactivado aparece no disponible y no admite reservas. Las reservas creadas en la agenda horaria anterior también bloquean su intervalo exacto en esta vista.

## Reservar un día

Al presionar un día se abre únicamente ese día, junto con su disponibilidad y el formulario:

- Médico solicitante.
- Nombre del paciente.
- RUT del paciente, con dígito verificador válido. Se normaliza al formato sin puntos y con guion.
- Tipo de cirugía.
- Inicio deseado, exclusivamente a la hora o media hora (`:00` o `:30`).
- Duración entera en minutos, de 1 a 1440 (hasta 24 horas).

La duración indicada por el médico abarca desde el inicio de preparación de anestesia hasta la salida del paciente. El sistema agrega el **tiempo medio de preparación configurado por Administración** (15 minutos por defecto). Las menciones de 15 minutos en los ejemplos corresponden a ese valor inicial.

Por ejemplo: inicio solicitado `09:30`, duración `90` minutos. El pabellón queda reservado de **09:15 a 11:00**. Se comprueba disponibilidad para los 105 minutos completos. Una duración de 20 minutos ocupa 35 minutos; no se redondea a una hora.

El comienzo de los 15 minutos previos no puede estar en el pasado. Se rechaza cualquier intersección con una reserva o uso ya registrado del mismo pabellón, aunque el conflicto solo afecte la preparación. Intervalos contiguos que se tocan exactamente sin superponerse sí se permiten.

Al pulsar un tramo verde posterior a una reserva, se ofrece el primer inicio compatible a la hora o media hora, dejando disponibles los 15 minutos previos de preparación. Por ejemplo, después de un término a las 11:00 se sugiere inicio a las 11:30, con preparación desde las 11:15. La sugerencia se precarga en el formulario del día.

Para las nuevas solicitudes posteriores a otra reserva del mismo pabellón en ese día, el inicio solicitado por el médico no puede quedar más de 30 minutos después del término anterior. La primera reserva del día elige su horario libremente; no se arrastra la última reserva de días anteriores. Una reserva que termina después de medianoche sí cuenta como anterior en el día en que termina. Los horarios ya registrados no se modifican retrospectivamente.

El selector muestra únicamente inicios que cumplen la continuidad, la preparación completa y al menos un minuto disponible para intervención; al confirmar se comprueba la duración completa solicitada. La validación se repite bajo bloqueo del pabellón y también se aplica al inicio de nuevas reservas de la agenda horaria anterior.

Si el término anterior fue a las 11:20, un inicio a las 11:30 no permite los 15 minutos de preparación y uno a las 12:00 supera los 30 minutos máximos. En ese caso no se ofrece una hora incompatible ni se acorta la preparación: se indica que ese tramo no admite inicio y debe seleccionarse otro. Los enlaces de sugerencia que dejaron de estar disponibles muestran un aviso y se vuelve a consultar la disponibilidad.

La preparación puede comenzar el día anterior y la intervención puede terminar el siguiente; se comprueban y colorean todos los días afectados. Tras guardar se vuelve al día seleccionado con la preparación en negro y la intervención en rojo, un mensaje con el horario completo y la reserva en el listado.

Los horarios se guardan en UTC y se muestran en America/Santiago. En cambios de hora se usan duraciones reales; se rechazan horas de inicio inexistentes o ambiguas. La escala continua contempla días de 23 o 25 horas.

Cada reserva muestra dentro de su tramo rojo el tipo de cirugía, el médico y el horario de intervención. Los 15 minutos anteriores se dibujan como un tramo negro separado y siguen bloqueados para otras reservas. En el recuadro, Horario Tramo abarca toda la indisponibilidad (preparación más intervención); Horario Reserva abarca desde el inicio solicitado hasta la salida. Duración Reserva cuenta solo los minutos solicitados y Tiempo Total agrega los 15 minutos de preparación. Las reservas contiguas conservan textos separados. Al pasar el mouse, enfocar con teclado o tocar el bloque se muestra un recuadro con esos datos más el nombre y RUT del paciente. Escape o un toque fuera cierran el recuadro. En tramos cortos o columnas estrechas el texto interior puede recortarse; el recuadro conserva el detalle completo sin agrandar artificialmente el intervalo horario.

El RUT es obligatorio para las nuevas reservas en ambas agendas. Las reservas existentes sin RUT mantienen sus datos y muestran «No registrado»; la migración no les asigna un identificador ficticio. Estos detalles siguen protegidos por autenticación y permiso de acceso a las intervenciones.

## Convivencia con la agenda anterior

Las dos agendas comparten las mismas reservas y el mismo bloqueo transaccional por pabellón, evitando superposiciones entre solicitudes simultáneas de cualquiera de ellas. La agenda horaria anterior conserva sus bloques de al menos una hora; la nueva agenda usa minutos más los 15 minutos de preparación.

La disponibilidad continua considera el uso real sin imponerle el mínimo artificial de una hora de la vista anterior. Una intervención abierta sigue bloqueando el resto del día actual hasta que se registre su salida; no se proyecta indefinidamente sobre fechas futuras.

En el detalle de una nueva reserva se distingue el inicio de preparación del pabellón, el inicio solicitado por el médico y la duración estimada. Se conserva el enlace para iniciar la intervención desde esa reserva durante su horario, sin imponer una hora adicional a las reservas nuevas de menor duración. Los eventos clínicos se registran con sus horas reales, no se completan automáticamente a partir de la estimación.

## Actualización

La migración agrega `planned_start_at` y reemplaza la restricción anterior por una que admite los dos tipos de reserva. Conserva las reservas existentes con sus horarios y el mínimo de una hora de su modalidad original.

Crear un respaldo antes de instalar y aplicar las migraciones con el servicio web detenido. Una vez registradas reservas nuevas de menos de una hora, no revertir la migración a la restricción anterior sin un plan para esos datos; una reversión directa puede fallar. Los nombres de pacientes y datos reales permanecen únicamente en la base de la VM, nunca en el repositorio.
