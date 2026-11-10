# Tablero de pabellones

Disponible en **Pabellones** desde la navegación o en `/pabellones/`. Requiere iniciar sesión y permiso para operar intervenciones.

Muestra una tarjeta por pabellón con una marquesina de color y el estado escrito:

| Color | Estado |
| --- | --- |
| Verde | Libre |
| Negro | En preparación |
| Rojo | En procedimiento |
| Café | No disponible |

La disponibilidad usa los mismos criterios del [panel de control](PANEL.md). Una intervención reservada antes del inicio de preparación es No disponible y muestra el motivo; al terminar la preparación pasa a En procedimiento.

Cada tarjeta muestra el nombre del pabellón, tipo de operación, médico responsable, fecha y hora de inicio de uso (evento 1, inicio de preparación) y término de uso (evento 9, salida del paciente). Si aún no se registra el evento correspondiente, muestra Pendiente. Los horarios se presentan en America/Santiago y utilizan las horas vigentes, incluidas las correcciones administrativas.

Cuando el paciente sale, la tarjeta conserva la última intervención y muestra **Finalizada**. Si el pabellón está activo, la marquesina queda verde (Libre); Finalizada describe la intervención y no reemplaza el estado de disponibilidad. Si el pabellón está desactivado, conserva la marquesina café con el motivo, aunque la última intervención haya finalizado.

Al crear una nueva intervención en el mismo pabellón, la tarjeta muestra esa intervención abierta en lugar de la última finalizada. Si nunca hubo una intervención, indica Sin intervenciones registradas. Se puede abrir el registro desde cada tarjeta y volver a consultar los datos con Actualizar; las alarmas de preparación consultan el estado cada 15 segundos y actualizan la vista al iniciar o terminar esa actividad. Los demás estados se consultan con Actualizar.
