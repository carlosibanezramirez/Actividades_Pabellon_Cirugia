# Abrir una reserva confirmada

La opción **Abrir reserva** del menú permite consultar reservas por fecha (hoy por defecto), pabellón y paciente/RUT/médico. Incluye las reservas que cruzan desde el día anterior y excluye las canceladas. Muestra paciente, cirujano, operación, horarios y estado.

**Abrir reserva** presenta sus datos sin permitir modificarlos. Se puede abrir anticipadamente cualquier reserva vigente, incluso días antes de su preparación, indicando un anestesista activo habilitado para anestesia. **Abrir preoperatorio y eventos** crea la intervención asociada y abre las actividades pendientes. No marca consentimientos ni eventos automáticamente.

Si ya hay una intervención asociada, **Retomar intervención** abre ese mismo registro. Una reserva finalizada permite consultar su intervención. Las reservas futuras permiten registrar sus consentimientos; las vencidas sin intervención no pueden abrirse para iniciar un registro. El servidor rechaza reservas canceladas, horarios inválidos, pabellones ocupados o anestesistas no habilitados.

Se utiliza el permiso de operación habitual y los bloqueos existentes para evitar crear intervenciones duplicadas. No requiere migraciones.


## Apertura anticipada y uso físico

La migración 0017 separa el preoperatorio abierto del uso físico del pabellón. Varias reservas pueden tener preoperatorios abiertos sin ocupar físicamente el mismo pabellón ni bloquear agendas o cambiar su estado operativo. El uso físico se activa al registrar Inicio de preparación del pabellón, manteniendo una sola intervención física en curso por pabellón.

Inicio y término de preparación pueden registrarse desde 30 minutos antes de `starts_at`, es decir, el inicio programado de la preparación incluido en la reserva. Antes de ese límite los botones quedan bloqueados y muestran la hora habilitada. Al alcanzarla, usar Actualizar si la página seguía abierta. Se respetan otros usos y reservas: el adelanto no puede superponerse al tramo anterior.

Los eventos posteriores requieren el cierre de preparación del pabellón y su secuencia habitual. La preparación de anestesia exige además ambos consentimientos, pero no debe esperar a la hora programada si esos requisitos están cumplidos. Las correcciones de preparación tampoco pueden adelantar su hora más allá del margen de 30 minutos.

Las reservas canceladas o vencidas siguen protegidas. La migración identifica como preoperatorios los registros de reservas sin eventos ni finalización; no modifica eventos históricos. Para revertir al esquema anterior sería necesario resolver primero los múltiples preoperatorios abiertos de un mismo pabellón.
