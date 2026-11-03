# POC semiautomática de escritorio

Lanzamiento desde C:\Users\labor\OneDrive\Documents\ChatGPT\Framwork:

```powershell
.\.venv\Scripts\python.exe -m ui.poc_dashboard
```

También disponible con `main.py --poc-ui` y referenciada desde la sección de
pruebas de Streamlit. ui/dashboard.py exporta DashboardPOC y conserva el
dashboard web existente; la implementación nativa está en ui/poc_dashboard.py.
No se inician navegadores, llamadas API ni ciclos al abrir el panel.

El operador configura cuenta, base QA (0–30), ciclos (1–100) y selectores.
Iniciar POC abre Patchright visible y el puente dinámico a SOCKS5/HTTP del
entorno privado. Se verifica HTTPS y se consulta el resolver GeoIP real.
La opción Exigir EU detiene la POC si no se acredita continente europeo.
El hostname europeo del gateway no garantiza una salida europea rotativa.

Después de navegar, el panel espera Continuar tras login. La autenticación y
cualquier revisión visual corresponden al operador; no se automatizan desafíos.
Al continuar se validan los selectores de sesión y video activo. Los ciclos
usan el scraper, OpenAI y el controlador de carga reales. La POC no publica
likes, comentarios ni compartidos. No usa un puerto 8081 ni latencias de ejemplo.

## Hilos y cancelación

Tk se toca únicamente en su hilo principal. Los valores se copian a un
POCSettings inmutable antes de crear el worker. Un hilo secundario mantiene
asyncio.run y comunica logs/métricas mediante queue.Queue y root.after.
El evento compartido es threading.Event; cualquier cancelación de Task se
envía con loop.call_soon_threadsafe. No se crea un asyncio.Event ligado a
otro hilo ni se actualizan botones desde el worker.

Detener interrumpe la pausa y solicita cancelación de una llamada de red
pendiente. Cerrar la ventana solicita parada y mantiene el bucle de Tk vivo
hasta acabar el hilo y sus cierres; no se abandona un hilo daemon con sockets.
El panel impide otro inicio mientras hay una prueba activa o la limpieza quedó
sin confirmar. La POC comparte el bloqueo farm.lock durante toda la prueba
y su limpieza, por lo que no corre en paralelo con otro supervisor del proyecto.

Las trazas de GeoIP, IA y carga se capturan de loggers específicos y se filtran
credenciales en URLs y claves API. La consola tiene tamaño acotado. Las filas
de rendimiento se leen de SQLite durante las fases y al finalizar, incluyendo
cancelaciones. No se muestran datos ficticios ni respuestas completas con
secretos. La cuenta/proxy provienen del entorno privado documentado; no hay
un formulario que duplique contraseñas en el panel.

Ver QA_LOAD_TELEMETRY.md para esquema, métricas y estados. Se verificaron el
arranque nativo y el controlador de hilos; la herramienta de control de ventanas
de este entorno no pudo activar la ventana para confirmar visualmente su diseño.
No se lanzó una POC contra TikTok vivo durante la entrega.

## Presentación y auditoría de botones

`presentar_ventana` se agenda con after_idle, solicita deiconify/lift/focus_set
y aplica -topmost durante 600 ms. Después restaura el valor anterior mediante
after. No usa focus_force ni SetForegroundWindow, ni repite intentos de robar
foco al navegador. Al cerrar se cancelan los callbacks pendientes y se restaura
la propiedad. Windows conserva la autoridad sobre el foco entre aplicaciones.

La comprobación local instrumentada confirmó ventana normal y mapeada,
foco Tk presente, -topmost desactivado tras el plazo y cierre SQLite confirmado.
Esto verifica el arranque de Tk; no garantiza prioridad sobre cualquier otra
ventana o política de escritorio de Windows.

`eventos_poc` registra admision, navegador_listo, esperando_login,
continuacion_solicitada y login_verificado, con run_id/cuenta/timestamp UTC.
Continuar reutiliza el contexto y carpeta de sesión ya abiertos; además
verifica los selectores de autenticación antes de consultar a OpenAI.

Parada segura es idempotente. El bloque de limpieza está protegido contra la
cancelación del worker y limita el cierre de contexto/runtime a 10 s cada uno.
Solo después de cerrar recursos y liberar slots/bloqueo se escribe
cierre_exitoso; un fallo escribe cierre_fallido. telemetry_saved indica si la
auditoría quedó confirmada. Un fallo SQLite nunca se presenta como escritura
exitosa. Las conexiones se cierran por operación.

Al cerrar una interfaz inactiva se registra su propio cierre con cuenta lógica
qa_desktop, distinta de una ejecución TikTok. Tk espera el trabajo de auditoría
antes de destruirse. Los fallos de escritura se informan en terminal; no se
fabrican eventos si el almacenamiento está indisponible.

El comando de lanzamiento configura logs INFO de QA y telemetría en terminal,
además de la consola del panel. No se vuelcan mensajes crudos de excepción ni
respuestas con secretos. Los registros indican el evento/fase que se confirmó
en SQLite y si el cierre o su auditoría quedaron pendientes.

Smoke móvil: ver MOBILE_PROXY_SMOKE.md. El panel añade un control explícito,
activado inicialmente, para rotar y verificar la IP antes de abrir Patchright.
Requiere el enlace real PROXY_ROTATION_URL; su ausencia bloquea ese inicio.

Actualización de proveedor: el control ahora valida según PROXY_MODE. La
configuración actual es rotating_residential de Proxy-Cheap y no exige una
API móvil. Ver PROXY_CHEAP_RESIDENTIAL.md para SOCKS5 y sesiones aleatorias.
# Panel por tarjetas

La interfaz separa identidad y sesión, red y seguridad, y auditoría de ciclos.
Los selectores conservan su ruta por defecto y se muestran en Opciones avanzadas.
Los campos se bloquean mientras hay una ejecución activa para evitar cambios
que no correspondan con la configuración congelada del worker.

Los indicadores de red comienzan en «Sin comprobar». El backend emite eventos
estructurados para proxy y GeoIP: en comprobación, verificado o con fallo. Un
fallo de GeoIP se destaca en rojo sin confundirlo con errores de cookies o IA.
Verificar HTTPS no acredita todo el tráfico del reproductor ni aislamiento VPN.

La tabla muestra las métricas recibidas desde SQLite. El progreso cuenta solo
ciclos únicos con estado `passed`: un ciclo correcto de cinco equivale a 20%.
Los fallos y cancelaciones permanecen visibles y no completan la barra.
La consola distingue persistencia, avisos y fallos mediante colores y texto.
Los eventos de control no se descartan cuando hay saturación de logs.

Todas las actualizaciones de widgets se procesan en el hilo de Tk mediante la
cola y `after()`. Se conserva la presentación temporal de 600 ms, la parada
idempotente y el cierre auditado. El panel no inicia tráfico al abrirse.

