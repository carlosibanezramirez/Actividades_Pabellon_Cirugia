# Reasignación automática por alargue

En **Administración → Configuración de pabellones → Reasignación por alargue**, configurar **Tiempo de alargue permitido** (minutos, por defecto 10, rango 0–1440).

El servicio Compose **overrun-monitor** comprueba cada 15 segundos las intervenciones con cirugía iniciada, uso físico activo y sin salida del paciente. Al cumplirse el margen desde el término reservado:

1. Busca la primera reserva siguiente del mismo pabellón, no cancelada ni pendiente de reprogramación, cuyo término todavía no haya pasado.
2. Comprueba otros pabellones activos del mismo tipo para el intervalo completo de esa reserva, incluida preparación. Respeta horarios, reservas, uso real y continuidad de 30 minutos. Urgencias no participa como origen ni destino.
3. Si encuentra una alternativa, cambia únicamente el pabellón. Conserva exactamente inicio, preparación, término, paciente, diagnóstico, médico y operación. Puede trasladarla aunque su inicio programado ya haya pasado; no traslada una intervención cuyo uso físico ya empezó. Si tiene un preoperatorio abierto, actualiza también su pabellón.
4. Registra origen, destino, intervención causante, horario y margen usado. El detalle de la reserva muestra un aviso; el perfil Administrador puede consultar la auditoría en Administración.

Sin alternativa, no modifica la reserva y reintenta en el siguiente ciclo mientras continúa el alargue. Solo se realiza una reasignación exitosa por intervención causante, evitando que cada ciclo mueva reservas adicionales. Si termina sin alternativa, continúa vigente el ajuste por salida del paciente de la versión anterior.

Los bloqueos de pabellones y reservas y la unicidad de la intervención causante evitan doble traslado o asignar un destino que se ocupó simultáneamente. No se envían correos en esta versión; la auditoría conserva la información para la futura integración.

## Despliegue

Aplicar la migración 0019 y ejecutar `setup_roles`. Construir y arrancar **web** y **overrun-monitor** con la misma revisión de código. El monitor funciona aunque no haya navegadores abiertos. Debe reconstruirse también al desplegar futuras versiones que cambien su código.

Comprobación manual opcional de una sola pasada: `docker compose run --rm overrun-monitor python manage.py monitor_overruns --once`. Para consultar el proceso: `docker compose logs --tail=50 overrun-monitor`.
