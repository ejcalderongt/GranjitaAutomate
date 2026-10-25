# Logs, trazas y feedback · v2.11

Fecha: 2026-10-24, America/Guatemala.

## Objetivo y acceso

Avanzado → Conexión y diagnóstico → Logs y trazas abre el visor. Consultar procesos, tiempos y errores; filtrar por tarea, serial o ID de ejecución; seleccionar un evento para ver su contexto y relaciones; exportar la ejecución y registrar qué se observó y qué se esperaba.

La finalidad es reconstruir procesos y comparar evidencias antes de cambiar reintentos, tiempos o recetas. No se generan ni aplican cambios de comportamiento a partir de texto libre de feedback. La siguiente mejora se implementa, verifica y versiona explícitamente.

## Persistencia y correlación

Base portable data/traces.sqlite3, con WAL y escrituras cortas, independiente de las bases de inventario y tareas. trace_events guarda fecha con milisegundos de Guatemala, versión del programa, run_id, span_id, parent_id, task_id cuando existe, proceso/paso, fase, estado, duración y metadatos permitidos. trace_feedback guarda notas y resultado esperado asociados al run_id. Una nota escrita por el usuario es contenido privado local.

Los spans hijos heredan tarea y contexto de dispositivo. En consultas paralelas se copia el contexto para mantener el mismo run_id y padres correctos. Los hilos Qt de procesos distintos inician su propio contexto; se pueden relacionar por task_id, serial o snapshot_id cuando están disponibles. No se promete una única traza global desde que abre Windows hasta todas las operaciones del día.

## Cobertura

| Proceso | Evidencia registrada |
| --- | --- |
| Aplicación | Inicio/cierre y fallos de comprobación mostrados en la interfaz |
| Panda | Apertura/comprobación, lista API, cambio de nombre/número y rechazo API |
| ADB | Descubrimiento de servidores, lista, validación, reconexión y consulta shell con tipo de comando |
| Inventario | Campo consultado, estado y código remoto cuando existe, sin almacenar su valor en la traza |
| Snapshots | Captura, restauración, archivo ausente y estado de recuperación/parcialidad |
| Identidad/mapa | Verificación y sincronización de posición |
| Automatización | Receta, sesión Appium, cada llamada de sesión, tipo/tamaño de respuesta y eventos auditables de likes/scroll |
| Errores | Clase, categoría, huella y últimos marcos archivo:línea:función, sin variables locales ni mensaje bruto |

Estados intermedios como snapshot Parcial o consulta restringida se conservan aunque la función haya retornado normalmente. Un end ok significa que la llamada devolvió, no que todas sus placas hayan conectado. Un intento de reconexión no se declara exitoso hasta la validación posterior. Los códigos HTTP/API conocidos se registran sin cuerpos de respuesta.

La auditoría de likes sigue siendo la fuente de verdad de interacciones y resultados en automation.sqlite3. Estas trazas agregan diagnóstico; no recalculan likes ni sustituyen su registro transaccional. Si falla guardar una traza, la operación conserva su comportamiento y no se repite por ese motivo. El visor informa cuántos eventos no pudieron guardarse durante ese proceso; pueden faltar pasos. Esto es distinto de la auditoría de acciones, cuya persistencia previa al clic sigue siendo obligatoria.

## Datos excluidos y límites

La traza estructurada no incluye cuerpos HTTP, salidas shell, XML de pantalla, imágenes/base64, texto de comentarios, comandos completos, claves, cookies ni mensajes de excepción brutos. Solo se admiten campos de metadatos y etiquetas acotadas. Se conservan identificadores privados de dispositivo/transporte para correlación, por eso la base y exportaciones permanecen fuera de Git.

El archivo bruto data/appium.log y los inventarios/auditorías anteriores son mecanismos independientes; no se incluyen en Exportar ejecución ni quedan filtrados retroactivamente por este módulo. El visor no exporta capturas de pantalla. El feedback manual no se redacta automáticamente: escribir observaciones sin credenciales.

Cada 1000 eventos escritos se purgan trazas de más de 30 días y se limita a los últimos 100000 eventos. La purga puede cortar una traza antigua; no es un archivo permanente de auditoría. Las notas de feedback no se purgan con esos eventos, aunque una traza antigua pueda dejar de estar disponible. Exportar antes si se necesita conservar evidencia completa. La purga no afecta tareas, métricas o snapshots.

El visor resume hasta 1000 eventos recientes; una exportación contiene hasta 10000 por ejecución e indica si posiblemente alcanzó el límite. Los errores mostrados son eventos, no incidentes ni placas únicas: una misma excepción puede producir eventos en varios niveles, y consultar un puerto de origen ya cerrado puede generar un error de conexión esperado. Las duraciones son por llamada; spans anidados o paralelos no deben sumarse para inferir tiempo total.

Las pruebas unitarias se etiquetan test y se excluyen de la vista normal. Durante la implementación se detectó que este entorno invoca unittest con un argv particular; se corrigió la detección y se reclasificaron los registros de desarrollo identificados, conservando copia previa en data/traces-before-source-filter.sqlite3. Los registros reales de validación permanecieron intactos.

## Consulta reproducible

```powershell
# Resumen y pasos más lentos de las últimas 10000 entradas operativas
.\.venv\Scripts\python.exe -m scripts.diagnostics
# Traza de una tarea y exportación local
.\.venv\Scripts\python.exe -m scripts.diagnostics --task-id UUID_TAREA --export data/traza-tarea.json
# Ejecución completa por ID de correlación
.\.venv\Scripts\python.exe -m scripts.diagnostics --run-id UUID_EJECUCION --export data/traza-ejecucion.json
```

Respaldar SQLite de la ventana principal sigue copiando granjita.sqlite3; no incluye automáticamente traces.sqlite3 ni automation.sqlite3. Exportar desde el visor o copiar coherentemente cada base con SQLite backup si se requiere conservarlas. Las trazas son locales y no se envían a un servicio externo.

## Validación y primer hallazgo

68 pruebas pasan con salida 0, incluyendo correlación entre hilos, ausencia de secretos/cuerpos/mensajes en las trazas, persistencia de feedback, etiquetado de tests y continuidad de operación si falla el log.

Comprobación real: una búsqueda generó 222 eventos con un solo run_id y 34 validaciones de transportes, que no equivalen a 34 placas únicas. Un piloto local de like completado produjo 40 eventos de receta, 37 vinculados directamente a su tarea y siete llamadas de sesión Appium terminadas; exportación verificada, sin errores en esa tarea. Se validó escritura/lectura de una nota técnica de feedback y se revisó el panel renderizado. SQLite integrity_check=ok.

En ese piloto task.like tardó aproximadamente 8.2 s y appium.session.open, 5.3 s. Es una sola muestra: sugiere medir el costo de apertura/instalación antes de optimizar la interacción. No se cambió la política de sesiones ni se añadieron reintentos para hacer parecer mejor el resultado.
