# Consentimientos preoperatorios

La intervención muestra dos actividades independientes en **Preoperatorio**:

- Firma Consentimiento Informado Operación.
- Firma Consentimiento Informado Anestesia.

Cada botón **Marcar como completada** registra la fecha/hora del servidor y el usuario. No hay hora de inicio ni duración. Pueden completarse en cualquier orden desde la creación del registro, antes o durante la preparación del pabellón, y hasta antes de comenzar la preparación de anestesia.

La preparación del pabellón conserva sus botones habituales. Para **Inicio de preparación de la anestesia**, ambos consentimientos deben estar registrados. La validación se aplica tanto al botón como al servidor, y los bloqueos impiden marcas duplicadas simultáneas. Una corrección de la preparación de anestesia tampoco puede situarla antes de la fecha de los consentimientos.

Los nueve eventos y sus estadísticas conservan sus identificadores y cálculos. Los consentimientos tienen un contador independiente y registro de consulta sin edición desde Administración para los usuarios con permisos correspondientes.

La migración 0016 crea la tabla sin inventar firmas para intervenciones anteriores. Las intervenciones que ya pasaron a anestesia o finalizaron mantienen sus datos y muestran Sin registro si faltan consentimientos históricos; pueden continuar sus eventos sin volver atrás. Las intervenciones que todavía no iniciaron preparación de anestesia deben completar los dos consentimientos para avanzar.

## Vista de actividades pendientes

Al completar una actividad, su tarjeta desaparece de la vista de trabajo y la página vuelve a la zona de pendientes. Los contadores separan **Eventos pre-operatorios** (de 2) y **Eventos cirugía** (de 9). El enlace **Ver historial de actividades y horas registradas** conserva la consulta de fechas, usuarios y correcciones; desde allí siguen disponibles las correcciones autorizadas. No se elimina ningún registro. Este ajuste de presentación no requiere migraciones.
