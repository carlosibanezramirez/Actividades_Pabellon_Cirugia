# Panel de control

Se accede desde **Panel de control** en el menú o en `/panel/`. Lo pueden consultar los perfiles con permiso para operar intervenciones.

## Estados actuales

Las cuatro tarjetas representan el estado actual de todos los pabellones, independientemente de las fechas de las estadísticas. Al presionar una tarjeta, se filtra la tabla de detalle, conservando las fechas elegidas. **Ver todos** elimina ese filtro. **Actualizar** vuelve a consultar los datos; no existe actualización automática en segundo plano.

- **Libre:** pabellón activo sin intervención abierta.
- **En preparación:** desde el evento 1 (inicio de preparación del pabellón) hasta el evento 2 (término). Mide el trabajo de aseo y preparación, no la espera previa ni la anestesia.
- **En procedimiento:** desde el evento 2 hasta el registro de salida del paciente (evento 9), que cierra la intervención. Incluye las etapas posteriores a la preparación, aunque aún no se haya iniciado la cirugía.
- **No disponible:** pabellón desactivado en Administración o reservado por una intervención sin inicio de preparación registrado. El detalle indica el motivo. Si conserva una intervención abierta, su registro sigue accesible.

Cada pabellón se cuenta en una sola tarjeta. Los estados se deducen de los registros; no son un historial de disponibilidad ni una medición por sensores.

## Fechas y estadísticas

El período predeterminado va desde el primer día del mes hasta hoy. Los controles de calendario permiten elegir ambas fechas, incluidas por completo, según America/Santiago. Un intervalo inválido muestra un error sin calcular estadísticas.

Se incluyen los eventos cuya hora vigente cae dentro del período, de todos los pabellones. La tarjeta de estado filtra únicamente la tabla de pabellones, no las estadísticas. La cantidad de intervenciones cuenta aquellas que tienen al menos un evento dentro del período; no equivale a intervenciones creadas ni finalizadas en esas fechas.

El gráfico y la tabla presentan seis mediciones con promedio, mínimo, máximo, cantidad de cierres registrados e intervalos completos:

| Medición | Inicio | Término |
| --- | --- | --- |
| Preparación de pabellón | 1: inicio de preparación del pabellón | 2: término de preparación del pabellón |
| Inicio de procedimientos | 2: término de preparación del pabellón | 3: inicio de preparación de anestesia |
| Preparación de anestesia | 3: inicio de preparación de anestesia | 4: término de preparación de anestesia |
| Anestesia | 5: inicio del procedimiento de anestesia | 8: término del proceso de anestesia |
| Cirugía | 6: inicio de cirugía | 7: término de cirugía |
| Salida del paciente | 8: término de anestesia | 9: salida del paciente |

Preparación de pabellón mide aseo y preparación. Inicio de procedimientos mide la espera hasta comenzar la preparación de anestesia. Salida del paciente mide la reacción del personal que realiza el traslado. Anestesia incluye el tiempo de cirugía; estas dos duraciones se superponen y no se suman como actividades independientes.

El inicio puede estar fuera del período; el evento de término determina la inclusión de cada medición. Cada intervalo completo contribuye una muestra y los promedios no se ponderan por pabellón. La cantidad global de eventos sigue contando los nueve tipos de eventos, no solo los seis que cierran mediciones.

Los intervalos sin ambos eventos no contribuyen al promedio y se muestran como `—`; un intervalo real de duración cero se muestra como `00:00:00`. Los tiempos se presentan como horas:minutos:segundos y pueden superar 24 horas.

Las correcciones administrativas modifican las estadísticas porque se utiliza la hora vigente, conservándose la auditoría original en la intervención. Si existieran intervalos negativos, se excluyen de las duraciones y el panel advierte cuántos requieren revisión.
