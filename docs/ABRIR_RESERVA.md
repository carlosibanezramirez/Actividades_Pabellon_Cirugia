# Abrir una reserva confirmada

La opción **Abrir reserva** del menú permite consultar reservas por fecha (hoy por defecto), pabellón y paciente/RUT/médico. Incluye las reservas que cruzan desde el día anterior y excluye las canceladas. Muestra paciente, cirujano, operación, horarios y estado.

**Abrir reserva** presenta sus datos sin permitir modificarlos. Durante el tramo reservado, incluida la preparación previa, pide un anestesista activo habilitado para anestesia. **Comenzar registro de eventos** crea la intervención asociada y abre las actividades pendientes. No marca consentimientos ni eventos automáticamente.

Si ya hay una intervención asociada, **Retomar intervención** abre ese mismo registro. Una reserva finalizada permite consultar su intervención. Las reservas futuras indican desde cuándo se pueden iniciar y las vencidas sin intervención no pueden iniciarse. El servidor rechaza reservas canceladas, horarios inválidos, pabellones ocupados o anestesistas no habilitados.

Se utiliza el permiso de operación habitual y los bloqueos existentes para evitar crear intervenciones duplicadas. No requiere migraciones.
