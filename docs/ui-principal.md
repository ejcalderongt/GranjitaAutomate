# Pantalla principal guiada · v2.10

Fecha: 2026-10-24, America/Guatemala.

## Uso cotidiano

1. **Conectar y comprobar.** Encender físicamente el rack y las placas; pulsar Conectar dispositivos. Abrir Panda si se necesita completar Habilitar/Escanear, OTG o autorización. Se mantiene la conciliación inicial existente.
2. **Revisar y elegir un dispositivo.** Buscar, seleccionar una fila, leer su diagnóstico y abrir Ver ficha. El orden físico asignado se conserva. La vista habitual muestra rack, posición, nombre, estado, reconocimiento Panda, diagnóstico y último snapshot.
3. **Preparar y ejecutar.** Snapshots permite crear o revisar respaldos lógicos; es opcional. Automatización abre el creador de tareas, donde se seleccionan los dispositivos del lote, la cantidad, scroll y horario. Elegir una fila en la ventana principal no obliga a limitar la tarea a esa única placa.

Se reemplazan los nombres visibles Snapshots 4.2 y Laboratorio Appium / Automate por Snapshots y Automatización. El número de subfase se mantiene en documentación e historial, no en el botón. El alcance de ejecución sigue siendo Granjita Lab.

## Indicadores

Cuatro tarjetas con números de 34 px y leyendas de 14 px: En línea (seriales físicos distintos con respuesta ADB), Aptos para tareas (fichas validadas con serial único sin conflicto), Requieren revisión (resto de fichas) y Fichas guardadas. Estos últimos son registros y pueden incluir duplicados históricos; no equivalen necesariamente al número de placas físicas. Mientras no se ha verificado el estado actual, se usa — y una explicación de datos históricos. Después de la búsqueda se muestra la hora de última comprobación de Guatemala. En línea no significa Internet ni medición eléctrica del socket.

## Menú Avanzado

| Sección | Funciones |
| --- | --- |
| Inventario | Actualizar seleccionada, actualizar todas, ver historial |
| Identidad y ubicación | Cambiar nombre, asignar rack/posición, asociar conexión a otra ficha |
| Conexión y diagnóstico | API Panda, configurar puertos ADB, mostrar servidores, revisión cada 30 segundos |
| Vista | Activos primero, mostrar columnas técnicas |
| Opciones generales | Respaldar SQLite, ayuda de conexión |

Los servidores y las columnas técnicas se ocultan inicialmente para simplificar la lectura; se pueden mostrar sin perder datos. La preferencia de activos primero y la revisión periódica conservan su persistencia existente. Mostrar servidores/columnas es una preferencia visual de la sesión. Cambiar nombre conserva su comportamiento de alias local; no renombra Android. Respaldar SQLite conserva su alcance de base principal, independiente de la base de tareas.

Todos los botones visibles, opciones del menú, filtros, indicadores y encabezados de columna tienen tooltips. Las ayudas explican propósito, estado histórico y límites de diagnóstico/recuperación. Automatización se distingue como acción principal.

## Validación

63 pruebas existentes pasan con salida 0. Se revisó el renderizado con el estilo real a 1280×930 y se verificaron tooltips de los botones y las opciones del menú. Se usaron registros guardados para la revisión visual; no representa una nueva búsqueda de placas. No se ejecutaron tareas ni se cambiaron nombres, posiciones o conexiones para esta mejora de interfaz.
