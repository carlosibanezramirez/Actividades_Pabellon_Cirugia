# Configuración de pabellones

En **Administración → Configuración de pabellones**, un administrador puede editar los tiempos medio y máximo de preparación para esta instalación. La apertura y el cierre se editan individualmente en **Administración → Pabellones**, tanto al agregar como al modificar un pabellón. Los superusuarios tienen acceso; el grupo Administrador necesita los permisos asignados por `setup_roles` y acceso al panel (`staff`).

| Parámetro | Valor inicial | Uso |
| --- | --- | --- |
| Tiempo medio de preparación | 15 minutos | Tiempo que se añade antes del inicio solicitado en las nuevas reservas continuas |
| Tiempo máximo de preparación | 30 minutos | Umbral de alarma para la preparación real en curso |
| Apertura de reservas de cada pabellón | 07:00 en nuevos pabellones | Primer inicio solicitado permitido en ese pabellón |
| Cierre de reservas de cada pabellón | 23:00 en nuevos pabellones | Hora máxima de término de la intervención reservada en ese pabellón |

Al actualizar, los pabellones existentes reciben el horario global vigente antes de la migración. Si era 06:00–23:00, conservan ese horario como punto de partida. Después cada pabellón puede tener horas distintas; modificar uno no afecta a los demás. Los campos horarios ya no aparecen en la configuración general de preparación.

Los tiempos son enteros positivos de hasta 1440 minutos. El máximo debe ser igual o mayor al medio. Apertura y cierre usan horas y minutos, dentro del mismo día, y el cierre debe ser posterior a la apertura. El panel administrativo registra los cambios en su historial.

## Preparación y reservas

El tiempo medio es una estimación configurable de planificación, no el promedio calculado de los registros. Se agrega antes del inicio de preparación de anestesia solicitado por el médico. Si se configura a 20 minutos y se solicita 07:00 con una duración de 60 minutos, el pabellón se ocupa de **06:40 a 08:00**.

La primera preparación puede comenzar antes de la apertura; el inicio solicitado debe respetar la apertura y la intervención completa debe terminar a más tardar al cierre. La agenda mantiene las 24 horas visibles y muestra en **celeste pálido** las franjas libres fuera del horario, sin enlaces de reserva. Una preparación reservada antes de la apertura aparece negra y ocupada. Las reservas antiguas y el uso real siguen visibles aunque queden fuera de un horario modificado posteriormente.

El cambio de tiempo medio afecta solo reservas nuevas. Las existentes mantienen sus fechas, duración y preparación almacenadas. Los formularios, sugerencias y validaciones del servidor utilizan la configuración vigente. La agenda horaria anterior también rechaza reservas fuera del período permitido.

Se conserva la regla de continuidad máxima de 30 minutos entre el término anterior y el nuevo inicio solicitado. Si se configura una preparación mayor de 30 minutos, esa regla impedirá encadenar nuevas reservas después de otra en el mismo día. El administrador puede ver esta relación en la sección de preparación.

## Alarma de preparación

La alarma compara el tiempo real desde el evento **Inicio de preparación del pabellón** hasta que se registra **Término de preparación del pabellón**. Aparece en las tarjetas de pabellones, en el detalle del panel y en la intervención. Al superar estrictamente el máximo muestra un aviso rojo de tiempo excedido y un contador.

Es una alarma visual con la vista abierta: no envía mensajes ni reproduce sonidos. El contador avanza cada segundo usando la referencia horaria del servidor; el estado se consulta cada 15 segundos y al volver a la pestaña. Al detectar el inicio o término de una preparación, la vista se actualiza para mostrar el estado vigente. El fin de la preparación retira la alarma; el aviso no impide registrar actividades.

El cambio del máximo se refleja en las preparaciones en curso en la siguiente consulta de estado. Si falla la consulta, se indica que el último estado no está actualizado. El endpoint solo entrega identificadores, inicio de preparación y umbral a usuarios autorizados; no incluye datos de pacientes.

## Instalación

Crear respaldo, reconstruir la imagen, detener web, aplicar `migrate`, ejecutar `setup_roles` si se necesitan actualizar permisos y volver a iniciar web. Las migraciones conservan las reservas existentes y trasladan el horario global vigente a cada pabellón antes de retirar los campos globales.

La reversión al esquema de horario global solo puede representar un horario: recupera el del primer pabellón y no conserva las diferencias individuales. Mantener un respaldo antes de revertir.
