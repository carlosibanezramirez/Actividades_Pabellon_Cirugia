# Nueva reserva mediante búsqueda de pabellón

La opción **Nueva reserva** del menú abre `/buscar-pabellon/`. Solicita doctor del catálogo, nombre y RUT del paciente, diagnóstico, operación del catálogo, día, hora de inicio y duración en minutos.

1. **Buscar pabellones disponibles** comprueba el intervalo completo: la preparación configurada antes del inicio solicitado y la duración hasta la salida del paciente. Respeta horarios individuales, continuidad, horas o medias horas, uso real, reservas activas y cruces de medianoche.
2. **Seleccionar y revisar** permite elegir un pabellón de los resultados y presenta todos los datos, inicio, término y preparación. Todavía no crea una reserva.
3. **Sí, confirmar y guardar** vuelve a comprobar la disponibilidad y registra la reserva con el diagnóstico. Si otra persona ocupó el pabellón, muestra un error y permite elegir otro resultado. Si cambió la preparación configurada, pide revisar el nuevo horario y confirmar otra vez.

Las búsquedas y revisiones duran 15 minutos, quedan asociadas a la sesión autenticada y no incluyen datos clínicos en la URL. Un formulario de confirmación conserva su propio pabellón elegido aunque se abra otra revisión. El diagnóstico aparece en el detalle de la reserva y se conserva al reprogramarla o cancelarla.

Requiere el permiso de operación habitual. La migración 0014 añade el diagnóstico; las reservas anteriores quedan con diagnóstico vacío. Reconstruir la imagen, detener web, aplicar migraciones y reiniciar web.
