# Subfase 4.2 · Snapshots lógicos y recuperación inicial

Versión de aplicación: 2.6. Fecha: 2026-10-24, America/Guatemala.

## Alcance

Un snapshot lógico versionado conserva serial físico, UUID de ficha, origen ADB, rack/posición/número Panda si están asignados, inventario consultable (sistema, paquetes, red, recursos y restricciones), identificador de arranque, actividad en primer plano como referencia y hasta 20 referencias de tareas con estado/fecha. No interpreta esas referencias como órdenes ni reanuda tareas inciertas.

Incluye archivos propios de /sdcard/Download/Granjita: nombres simples .json/.txt, sin subdirectorios, hasta 32 archivos de 16 KiB cada uno. Es un área administrada para configuraciones y pequeños puntos de control, no una copia de Downloads ni de fotos/documentos personales. Archivos no permitidos o errores de consulta dejan el snapshot Parcial; nunca reemplaza la selección del último Completo. Los archivos se verifican por tamaño y SHA-256 antes/después de leer. No se detienen aplicaciones durante la captura: el inventario es una serie de consultas fechadas, no un congelamiento atómico del sistema Android.

No respalda datos internos, cookies, sesiones ni permisos de aplicaciones ajenas, ni las preferencias internas del laboratorio. No clona particiones, no usa root y no garantiza restauración integral de un teléfono. El primer lote real encontró vacía el área administrada; respaldó inventario y estado consultable. La única carga de archivo inicial proviene de la prueba controlada de recuperación.

## SQLite y respaldo

La migración v5 crea respaldo previo granjita-antes-v5.sqlite3. En la misma granjita.sqlite3 se agregan:

| Tabla | Contenido |
| --- | --- |
| device_checkpoints | ID, identidad, fecha, Completo/Parcial, manifiesto JSON versionado, SHA-256 |
| checkpoint_files | ID de snapshot, nombre relativo, contenido BLOB, tamaño y SHA-256 |
| recovery_events | Identidad, snapshot, fecha, estado y detalle de captura/recuperación/error |

No se externalizan los archivos respaldados: un respaldo SQLite contiene manifiestos y BLOB, además de inventario y mapa físico. La cola original sigue en automation.sqlite3; el snapshot copia referencias de tareas sin cambiar sus estados. Para respaldar la operación completa conservar ambas bases mediante sus mecanismos de copia coherente; Respaldar SQLite de la ventana principal copia granjita.sqlite3. Los respaldos reales y evidencias permanecen en data/, excluido de Git. No hay borrado automático/retención en esta entrega; el tamaño puede crecer.

Se generó un respaldo inicial posterior al lote en data/backups/granjita-4-2-inicial.sqlite3. Sigue siendo una copia local en este equipo, no un respaldo externo contra pérdida del disco.

## Flujo de inicio

1. Encender equipo/rack y completar el arranque físico necesario.
2. Abrir GranjitaAutomate: abre Panda si falta, concilia y valida identidades, conserva el mapa físico local.
3. Una vez terminada la primera conciliación exitosa se inicia el trabajador de snapshots, sin bloquear la interfaz.
4. Si una placa elegible no tiene snapshot Completo, crea la primera base. Si existe, toma el último Completo y verifica identidad, manifiesto, archivos y sys.boot_completed=1.
5. Repone solamente archivos administrados AUSENTES, usando creación sin sobrescritura y lectura posterior. Los existentes iguales quedan intactos. Los diferentes permanecen en el teléfono y se registran para revisión. La restauración de varios archivos es por archivo, no una transacción remota global; si falla una parte queda evidencia y se puede verificar otra vez.
6. Compara inventario actual con el guardado y registra campos distintos sin restaurar red, permisos, aplicaciones, pantalla o ajustes Android. Las diferencias normales de batería/IP/almacenamiento también aparecen.

El arranque automático no convierte el estado posterior en una nueva base ni reemplaza un snapshot al encontrar diferencias. Para actualizar el último estado guardado usa Crear snapshot seleccionada o Crear snapshots de todas las elegibles. No hay captura periódica, al cerrar, ni enganche automático después de tareas en esta versión. Los cambios posteriores a la última captura no pueden recuperarse desde ella.

Solo son elegibles fichas validadas con serial utilizable único, sin conflictos de identidad. No se migra una copia a otra placa por IP/posición. Las desconectadas, ambiguas o que aún no completaron arranque requieren conciliar y volver a verificar desde el panel; no hay bucle de reintentos ni garantía de encendido físico. No se reordenan ni renombran dispositivos en Panda durante la recuperación.

## Operación

Botón Snapshots 4.2: crear seleccionada/todas, ver historial, manifiestos e incidencias y verificar/recuperar seleccionada. La tabla principal muestra último snapshot y último resultado de recuperación. Las fechas son de Guatemala.

```powershell
# Búsqueda actual, snapshot de todas las identidades elegibles
.\.venv\Scripts\python.exe -m scripts.snapshots --capture --all
# Verificar/recuperar archivos ausentes de una ficha explícita
.\.venv\Scripts\python.exe -m scripts.snapshots --device-id UUID_INTERNO
# Prueba controlada: crea, respalda, elimina y recupera UN archivo propio aleatorio
.\.venv\Scripts\python.exe -m scripts.test_snapshot_recovery --device-id UUID_INTERNO
```

La prueba deja el pequeño archivo de evidencia en el área administrada para no contradecir la base capturada. No borra datos existentes. La CLI devuelve error si alguna placa falla o genera snapshot Parcial. No se confunde salida del lote con éxito de todas.

## Validaciones de esta entrega

- 50 pruebas con salida 0: integridad de manifiesto/BLOB, bloqueo ante corrupción o identidad incorrecta, rutas, conservación de archivos distintos, recuperación de ausentes, arranque incompleto, bases parciales y secuencia de inicio después de liberar el trabajador de conciliación.
- Primer intento encontró transportes guardados obsoletos y registró errores. Se corrigió la CLI para buscar y validar antes del lote.
- Pasada actualizada: 28/28 fichas elegibles con snapshot Completo, salida 0. No representa todas las placas físicas: identidades ambiguas y desconectadas quedan excluidas. No se alteraron las asociaciones históricas para aumentar cobertura.
- Recuperación real en una placa: archivo propio JSON eliminado y recuperado byte por byte; se registraron diferencias de inventario sin modificar los ajustes.
- SQLite integrity_check=ok y esquema 5; 28 seriales con snapshot completo. Mapa físico aún sin asignaciones, conservado como pendiente, sin inventar rack/posición.
- Panel renderizado revisado. No se realizó corte completo del rack ni restauración de datos de aplicaciones externas.

Referencias oficiales: https://developer.android.com/tools/adb y https://developer.android.com/identity/data/backup. El respaldo Android de cada aplicación depende de sus mecanismos/permisos; este snapshot lógico es independiente de Auto Backup de Google.
