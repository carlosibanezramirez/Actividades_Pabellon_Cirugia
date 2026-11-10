# Resumen de ocupación semanal

En **Ocupación semanal** (`/ocupacion-semanal/`), elegir una fecha consulta su semana de lunes a domingo. Los pabellones se presentan uno debajo del otro, cada uno con siete tarjetas tituladas por fecha.

Cada tarjeta muestra la cantidad de reservas activas (pendientes o en curso, cuyo término no ha pasado), los tramos libres exactos, sus minutos y el total disponible. Una reserva que cruza medianoche se cuenta en cada día en que ocupa tiempo. No se muestran nombres ni RUT de pacientes.

Los tramos se calculan descontando tanto reservas —incluida su preparación previa— como uso real del pabellón, sin duplicar los intervalos superpuestos. Se respetan la apertura y el cierre de cada pabellón; no se ofrecen minutos ya pasados ni pabellones inactivos. Los tiempos libres incluyen el espacio necesario para la preparación de una nueva reserva. El enlace **Ver día y reservar** lleva al formulario existente, que valida las horas o medias horas de inicio, preparación, continuidad máxima y disponibilidad completa de la duración solicitada, incluso si termina al día siguiente.

La vista utiliza los mismos permisos de operación que la agenda semanal y no requiere cambios de base de datos.
