# Panel de control

Se accede desde **Panel de control** en el menú o en `/panel/`. Lo pueden consultar los perfiles con permiso para operar intervenciones.

## Estados actuales

Las cuatro tarjetas representan el estado actual de todos los pabellones, independientemente de las fechas de las estadísticas. Al presionar una tarjeta, se filtra la tabla de detalle, conservando las fechas elegidas. **Ver todos** elimina ese filtro. **Actualizar** vuelve a consultar los datos; no existe actualización automática en segundo plano.

- **Libre:** pabellón activo sin intervención abierta.
- **En preparación:** intervención abierta desde su creación hasta antes del evento 5, inicio del procedimiento de anestesia.
- **En procedimiento:** desde el evento 5 hasta el registro de salida del paciente (evento 9), que cierra la intervención.
- **No disponible:** pabellón desactivado en Administración. Este estado tiene prioridad visual; si conserva una intervención abierta, su registro sigue accesible en el detalle.

Cada pabellón se cuenta en una sola tarjeta. Los estados se deducen de los registros; no son un historial de disponibilidad ni una medición por sensores.

## Fechas y estadísticas

El período predeterminado va desde el primer día del mes hasta hoy. Los controles de calendario permiten elegir ambas fechas, incluidas por completo, según America/Santiago. Un intervalo inválido muestra un error sin calcular estadísticas.

Se incluyen los eventos cuya hora vigente cae dentro del período, de todos los pabellones. La tarjeta de estado filtra únicamente la tabla de pabellones, no las estadísticas. La cantidad de intervenciones cuenta aquellas que tienen al menos un evento dentro del período; no equivale a intervenciones creadas ni finalizadas en esas fechas.

Para los nueve eventos se informa cantidad de registros. Para los eventos 2 al 9 se calculan promedio, mínimo y máximo del tiempo desde el evento inmediatamente anterior de la misma intervención. El evento anterior puede estar fuera del período; el evento que cierra cada intervalo determina su inclusión. Un intervalo completo contribuye una muestra y los promedios no se ponderan por pabellón.

El primer evento no tiene una duración previa. Los intervalos sin ambos eventos no contribuyen al promedio y se muestran como `—`; un intervalo real de duración cero se muestra como `00:00:00`. Los tiempos se presentan como horas:minutos:segundos y pueden superar 24 horas. El gráfico compara los promedios entre los ocho intervalos.

Las correcciones administrativas modifican las estadísticas porque se utiliza la hora vigente, conservándose la auditoría original en la intervención. Si existieran intervalos negativos, se excluyen de las duraciones y el panel advierte cuántos requieren revisión.
