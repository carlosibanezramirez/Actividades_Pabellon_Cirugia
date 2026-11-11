# Nueva reserva mediante asignación automática

La opción **Nueva reserva** del menú abre `/buscar-pabellon/`. Solicita doctor del catálogo, nombre y RUT del paciente, diagnóstico, operación del catálogo, día, hora de inicio y duración en minutos.

1. **Buscar y asignar pabellón** comprueba el intervalo completo: la preparación configurada antes del inicio solicitado y la duración hasta la salida del paciente. Respeta horarios individuales, continuidad, horas o medias horas, uso real, reservas activas y cruces de medianoche. Elige al azar, con igual probabilidad, uno de los pabellones que cumplen las condiciones. No permite selección manual.
2. Presenta los datos y el pabellón asignado en un recuadro para revisarlos. Todavía no crea una reserva.
3. **Sí, confirmar y guardar** vuelve a comprobar el pabellón asignado y registra la reserva con diagnóstico. El formulario muestra **Reserva confirmada** con el mismo pabellón enmarcado y un enlace al detalle. Recargar esta página no vuelve a guardar. Si otra persona ocupó el pabellón, se pide una nueva búsqueda; no se sustituye la asignación durante la confirmación. Si cambió la preparación, se revisa el horario y se confirma otra vez.

Las asignaciones pendientes duran 15 minutos y quedan asociadas a la sesión autenticada, sin datos clínicos en la URL. Los campos manipulados en el envío no cambian el pabellón asignado en el servidor. El diagnóstico aparece en el detalle y se conserva al reprogramar o cancelar.

Requiere el permiso de operación habitual. La migración 0014 de la versión anterior añade el diagnóstico; este ajuste de asignación automática no añade migraciones.
