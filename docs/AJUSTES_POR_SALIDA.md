# Ajuste automático por salida del paciente

Al registrar **Salida del paciente del pabellón** en una intervención asociada a una reserva, el término de la reserva se ajusta a la fecha y hora real de salida:

- Si termina antes, libera el resto del tramo reservado. No se aplica el mínimo histórico de una hora al uso efectivo de una intervención con reserva.
- Si termina después y el tramo estaba libre, extiende la reserva hasta la salida real.
- Si la extensión coincide con otras reservas activas del mismo pabellón, muestra el alargue en café. Reduce las reservas alcanzadas desde su inicio, manteniendo su término previsto. Conserva su tiempo de preparación antes del nuevo inicio clínico, por lo que disminuye la duración disponible.

Cuando una reserva pierde todo su tiempo o no queda espacio útil después de la preparación, se conserva sin cancelarse, marcada **Sin tiempo disponible / Pendiente de reprogramación**. No bloquea tiempo ni permite iniciar la intervención. Aparece en el día de la agenda y en Abrir reserva con un botón para reprogramar. Al reprogramarla se recuperan la preparación y duración originalmente solicitadas; admite también preoperatorios abiertos sin uso físico iniciado.

Los ajustes mantienen una copia del horario previo al primer ajuste automático y un historial por cambio, con fechas anteriores/nuevas, intervención causante y usuario que registró la salida. La reserva no se elimina. El detalle muestra el historial; Administración permite su consulta de solo lectura a usuarios autorizados.

El registro de salida, los ajustes y la reducción de reservas siguientes se guardan en una sola transacción, con el pabellón y las reservas bloqueados. Las reservas canceladas no generan conflictos. Los tramos se recortan por día para mostrar cruces de medianoche.

Las correcciones autorizadas de la hora de salida también actualizan el término de la reserva y ajustan nuevos conflictos. No restauran automáticamente tiempo ya retirado a otras reservas, que podría haberse reprogramado; estas mantienen el historial y se pueden reprogramar explícitamente.

La migración 0018 incorpora los campos y el historial. No modifica retrospectivamente las reservas de intervenciones cuya salida ya estaba registrada.
