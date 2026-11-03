# Bootstrap y resiliencia

Actualizado: 2026-10-28, America/Guatemala.

## Operación

`Iniciar-Granja.cmd` arranca el modo continuo. También puede usarse:

```powershell
.\.venv\Scripts\python.exe main.py --start-farm --cycles 0
.\.venv\Scripts\python.exe main.py --smoke-test 3 --cycles 1
```

La aplicación global y su activity proceden de `config/tiktok_app.json`.
El smoke conecta el inventario configurado, pero solo despierta y lanza la app
en su subset fijo. Cada lanzamiento verifica identidad, componente instalado,
proxy, reglas de firewall y salida HTTPS antes de abrir TikTok.

## Secuencia

1. Validar el binario físico y adquirir el lock exclusivo de la granja.
2. Consultar en paralelo 5037/5038. Si falta un servidor local, ejecutar
   `start-server` en ese puerto; nunca matar ni reiniciar servidores existentes.
3. Reconectar hasta 40 direcciones configuradas simultáneamente. Una ruta
   `offline` recibe `disconnect IP:PUERTO` y `connect IP:PUERTO` en su servidor;
   nunca se ejecuta un disconnect global. Releer `devices -l` para acreditar éxito.
4. Leer y contrastar el serial físico, enlazar AGX y actualizar SQLite WAL.
   Esperar hasta 30 segundos por hardware que todavía está encendiendo.
5. Recuperar leases anteriores de workers terminados: verificar identidad,
   detener app, retirar solo cadenas propias y restaurar proxy. Limpiar XML
   temporales conocidos; conservar auditoría, manifiestos, capturas y evidencias.
6. Validar proxies reales y API key. Crear workers en paralelo según capacidad.
   En cada placa: WAKEUP, MENU para desbloqueo básico sin credenciales,
   force-stop, proxy/firewall, arranque global y comprobación de cuenta/feed.

Un PIN o patrón requiere intervención del operador. La presencia de un feed
es una heurística de sesión, no una prueba de autenticación del servidor.

## Parámetros

| Flag | Predeterminado | Uso |
| --- | --- | --- |
| `--devices` | 40 | Máximo de workers; no inventario exigido |
| `--bootstrap-parallelism` | 40 | Reconexiones y arranques paralelos |
| `--bootstrap-timeout` | 30 s | Ventana para encendido de hardware, máximo 300 s |
| `--worker-timeout` | 180 s | Watchdog sin heartbeat, mínimo 30 s |
| `--auto-heal-attempts` | 2 | Reinicios recuperables por placa, máximo 5 |
| `--shutdown-grace` | 180 s | Cierre cooperativo antes de terminar procesos |

`--plan` no inicializa servidores, reconecta, limpia sesiones ni crea workers.
`--bootstrap-parallelism 1` permite volver al arranque escalonado de 2–5 segundos.

## Aislamiento de fallos

El supervisor detecta la salida de un worker o la falta de heartbeat. Termina
solo el proceso congelado y libera su admisión API. Las consultas usan
`api_slots` y `api_rate` en SQLite; la señal de parada compartida no tiene locks
que pueda abandonar un proceso terminado. La llamada API tiene timeout y los
slots tienen caducidad adicional como última protección.

La recuperación se ejecuta en threads separados, manteniendo a los otros workers
activos. Publica Reconectando, Recuperando o Cuarentena en el dashboard.
También detecta pérdida de la configuración de proxy y comprueba periódicamente
la salida HTTPS. Nunca se reasigna un proxy cuya limpieza no se confirmó:
se mantiene en cuarentena hasta recuperar la placa correcta.

Los reintentos son acotados y conservan directorios separados. Si la auditoría
contiene un intento de like o envío de comentario, no se repite automáticamente
ese trabajo; se recuperan los recursos y se registra fallo para revisión. Las
colisiones de IP siguen siendo una condición explícita de parada compartida.

## Recuperación persistente

Cada worker guarda `supervisor_lease.json` con identidad, ruta, owner, token API
y PIDs, además de los leases de proxy/firewall. El siguiente arranque comprueba
que los procesos anteriores hayan terminado. Un PID vivo o una identidad
incierta impiden limpiar o liberar su reserva. Se soportan manifiestos anteriores
cuando contienen información suficiente para verificar la propiedad.

Los únicos XML temporales eliminados son `window_dump.xml`,
`window_dump.pending.xml`, `panda_wait.xml` y `panda_auth.xml`, dentro de directorios
de workers propios y terminados. No hay borrado recursivo de sessions ni flush
global de iptables. El resumen queda en `sessions/bootstrap-recovery.json`.

## Medición

El dashboard muestra el tiempo ADB y el tiempo incluyendo verificación de
identidad; también se conservan en `logs_granja`, run_id `bootstrap`.
La observación del 2026-10-28 encontró 34 placas verificadas sin incidencias:
39,83 ms para inventario ADB y 1.135,29 ms incluyendo identidad. Los transportes
ya estaban conectados. Esto no acredita un arranque después de un corte.

La suite comprueba 34 reconexiones concurrentes, reinicio aislado, watchdog,
limpieza con propiedad verificada y recuperación de API al terminar un proceso.
El objetivo de reconexión inferior a cinco segundos depende de que Panda y las
placas estén disponibles; el tiempo de boot de Android, root/firewall y login
no tiene una garantía de cinco segundos.
