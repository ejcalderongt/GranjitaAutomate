# QA físico de Panda — 2026-11-02

Validación de entrega: **329 pruebas aprobadas**. El preflight real vinculó
02, 04, 05, 06, 09 y 10 sin capturas, gestos ni llamadas a OpenAI. La captura
real y el gesto masivo quedan pendientes de admisión explícita del operador.

`main_panda.py` añade un flujo separado del navegador: selección explícita por
número visual, asociación inmutable por onlySerial, captura PNG y visión opt-in.
No publica likes ni comentarios ni cambia redes, permisos o configuración Android.

Se usa la [API Android documentada de Panda](https://doc.some3c.com/panda-manual/api-documentation):
WebSocket local `ws://127.0.0.1:22222/`, acciones `list`, `Screen` y
`pointerEvent` tipo `6`. No se presupone un servidor HTTP en 8080 ni panda-cli.
La instalación debe permitir esos comandos; los permisos/licencia se comprueban
por respuesta, nunca se dan por habilitados por el nombre del producto.

## Comandos

Solo inventario y vinculación; sin capturas, OpenAI ni gestos:

```powershell
.\.venv\Scripts\python.exe main_panda.py --devices 02 04 05 06 09 10
```

Tras revisar manualmente que esas placas están en el feed de prueba, ejecución
de cinco ciclos de captura y desplazamiento **sin enviar imágenes a OpenAI**:

```powershell
.\.venv\Scripts\python.exe main_panda.py --devices 02 04 --cycles 5 --hold-seconds 8 --execute-read-only --ready
```

Agregar `--allow-vision-upload` autoriza el envío de **capturas completas** a
OpenAI mediante `gpt-4o`. No ejecutar sobre notificaciones, mensajes, login ni
cuentas que contengan información privada no autorizada. El modelo ve una
imagen estática, no el video ni el audio. Las transcripciones no son prueba
de autenticación ni una decisión definitiva de moderación.

Capturas en `screenshots/<run_id>/snapshot_<id>.png`, privadas y excluidas de
Git. Cada captura Panda se genera en un directorio nuevo y se valida antes de
normalizarla; no se acepta un PNG residual. Archivos auxiliares se conservan
localmente para diagnóstico; requieren una política privada de retención.

## Concurrencia y auditoría

Capturas limitadas a cuatro tareas; visión con semáforo configurable de 1 a 8
(por defecto 2), sin reintentos automáticos. Pausa determinista configurable
entre 8 y 22 segundos y cancelable, sin simulación de conducta humana. Los
fallos de una placa producen una fila y no detienen las demás. No se selecciona
`all` ni se envían comandos a números sin vínculo unívoco. Se releen identidad,
transporte y estado antes de capturar y antes del swipe; no se acredita una
verificación adicional del serial vía USB por usar onlySerial del inventario.

La SQLite `telemetria_panda.db` contiene `auditorias_panda`, con timestamp UTC,
run_id, ciclo, placa, informe visual JSON, latencia y estado operativo. Es una
base **privada con contenido**, separada de `telemetry_qa.db`, que solo almacena
métricas y códigos sin imágenes, transcripciones ni respuestas. Ambas quedan
fuera de Git. SQLite usa WAL, transacciones por lote y conexiones cortas fuera
del bucle. Primero se confirma la escritura del lote; luego un solo mensaje
Panda solicita el gesto para todas las placas elegibles.

`orden_aceptada` significa respuesta de Panda: no confirma movimiento físico ni
cambio de video. Si la orden queda incierta, se registra como tal y se detiene
el lote sin reenviarla. Ctrl+C cancela; las conexiones WebSocket se cierran y
las órdenes en curso tienen un timeout acotado antes de liberar el bloqueo.
El bloqueo compartido impide competir con una POC web activa en este workspace.

Consulta real de inventario del 2026-11-02: Panda respondió con 34 entradas y
onlySerial presente. Esta versión omite `status`, aunque el ejemplo del manual
lo incluye. La presencia en `list` se trata como conexión observada, no como
garantía de salud; si aparece un estado explícito offline se bloquea. Las
capturas y órdenes requieren confirmación independiente. No se ejecutaron
capturas, llamadas Vision ni gestos en esta comprobación de inventario.

## Utilidad ADB opcional

`core/adb_wrapper.py` permite seleccionar una ruta explícita del pool Panda,
capturar por exec-out y ejecutar un swipe proporcional con orientación vertical
comprobada. No se usa como sustituto silencioso de una API Panda que falle.
No se instalaron dependencias adicionales de OpenCV: Pillow y el SDK existente
bastan para este flujo.
