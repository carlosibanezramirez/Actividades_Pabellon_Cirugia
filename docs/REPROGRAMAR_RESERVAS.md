# Reprogramación de reservas

En la agenda semanal o en el detalle de un día, hacer clic sobre un bloque reservado abre **Editar reserva**. También se abre con Enter o espacio al enfocar el bloque. Al pasar el cursor se conserva la información emergente.

El cuadro presenta la fecha, el pabellón actual y la hora de inicio solicitada. Se puede cambiar cualquiera de estos tres datos. La duración, preparación previa almacenada, médico, cirugía, paciente, RUT y autor originales se conservan. Las reservas horarias antiguas mantienen su duración y formato original.

**Confirmar cambios** valida todo el tramo, incluida la preparación y cualquier continuación al día siguiente, con el horario del pabellón destino y la regla de continuidad de 30 minutos. La propia reserva se excluye de las comprobaciones. Un error mantiene los datos originales; un cambio válido actualiza el mismo registro, libera el horario anterior y abre la semana del nuevo pabellón y fecha.

Solo se pueden reprogramar reservas futuras sin intervención asociada. Se requiere el permiso de operación utilizado por la agenda. Los bloqueos de PostgreSQL evitan reservar simultáneamente el mismo tramo y una revisión firmada impide sobrescribir un cambio realizado mientras otro usuario tenía el cuadro abierto. En ese caso se debe cerrar y volver a abrir la reserva.

No requiere migraciones de base de datos.
