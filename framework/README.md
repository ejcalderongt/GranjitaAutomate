# Panda Box: QA Android, 140 placas

## Credenciales del proyecto

`OPENAI_API_KEY` se carga en el entorno del backend desde `.env` al abrir `main.py`,
el launcher o el dashboard. El archivo esta excluido de Git y tiene permisos de
lectura limitados al usuario, administradores y SYSTEM. No se muestra su contenido
en la interfaz. Una variable definida explicitamente en el proceso tiene prioridad.
La configuracion sigue la recomendacion de [OpenAI Docs](https://developers.openai.com/api/reference/overview)
de cargar credenciales en el servidor mediante variables de entorno.

Despues de cambiar la clave, reiniciar el dashboard. Para ejecutar pruebas sin
usar la credencial real:

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
```

## Configurar y ejecutar desde el dashboard

En este equipo quedo instalado el [proxy local de laboratorio](docs/local-proxy.md):
tres puertos reales en Windows con salida publica compartida, sin contratar un
proveedor externo. El dashboard lo identifica como laboratorio y sus entradas
ya estan preconfiguradas. Las instrucciones siguientes sobre proveedor e IPs
distintas corresponden al perfil de produccion.

En **Configuracion y Pruebas  Configurar proxies**, completa IPv4 del endpoint,
puerto e IP publica de salida del proveedor. Activa cada fila real y pulsa
**Guardar proxies**. Los ejemplos permanecen deshabilitados; el motor usa
endpoints HTTP sin usuario/contrasena, autorizados por IP con el proveedor.

En **Panel de Control  Lanzar automatizacion**, elige Smoke test o Granja,
numero de placas y ciclos. Para la primera ejecucion, usa Smoke test, 3 placas
y 1 ciclo; los primeros tres proxies deben estar habilitados con salidas distintas.
El panel indica si OPENAI_API_KEY esta configurada en el entorno del servidor.

**Detener automatizacion** solicita cierre cooperativo mediante un archivo de
control: los workers cierran y limpian sus recursos. La salida del proceso aparece
en el mismo panel. No se fuerza la terminacion desde el boton. El controlador
gestiona el proceso que se haya iniciado desde ese servidor de dashboard;
una ejecucion iniciada desde consola se detiene con Ctrl+C en su consola.

Las conexiones antiguas por IP sin identidad activa se ocultan por defecto en
el inventario; el interruptor correspondiente permite consultarlas sin borrar
su historia. El inventario ordena las placas conectadas primero.

## Control de cuenta antes de IA

En `--start-farm` y `--smoke-test`, el worker espera la UI inicial y hace un dump
comprimido independiente antes de crear el cliente OpenAI. `core/selectors.py`
busca acciones visibles de login/registro en espanol/ingles y la pestana Perfil,
Profile o Me (tambien IDs conocidos de perfil). Un login visible o la ausencia
de Perfil despues de cargar el feed devuelve **Pendiente Cuenta**. Si el login
impide cargar el reproductor, se comprueba despues de la primera ventana fallida
sin inferir ausencia de cuenta solo por un Perfil que todavia no cargo.

La misma comprobacion se repite antes de cada video. Se respetan paquete, visibilidad
y bounds; un texto del post que menciona iniciar sesion no se interpreta como
boton salvo que forme parte de un control pulsable. XML invalido, otro paquete
o perdida de ADB son errores tecnicos, no una clasificacion de cuenta ausente.

La placa se detiene sin navegar ni consultar IA, se cierra TikTok y se limpia red.
Su estado `Pendiente Cuenta` permanece tras refrescos de inventario y cierre del
supervisor, sin detener a las otras placas cuando la limpieza fue exitosa. Se
libera el proxy incluso durante un smoke test: la placa se excluye del conjunto
valido de esa prueba, conservando la IP observada como registro rechazado, antes
de liberar el lease. Asi otra placa puede utilizar ese recurso sin una colision
con el historial del dispositivo descartado. Si no se pudo limpiar, el lease
permanece en cuarentena y se mantiene la politica de parada por fallo de red.

SQLite conserva `cuenta_estado`, `cuenta_motivo`, `cuenta_verificada_en` e historial.
Streamlit muestra **Placas sin Cuenta Activa**, aviso amarillo y filas ` Pendiente
Cuenta`. Las cuentas aun no comprobadas se muestran por separado; cero casos
detectados no equivale a comprobar todas las sesiones. El resumen de una ejecucion
con placas pendientes indica `revision_cuentas`, no una prueba fisica aprobada.

El operador configura las cuentas manualmente. Una nueva ejecucion controlada
vuelve a comprobar la UI y puede retirar el estado pendiente si resulta compatible.
El resultado se guarda en `auth_check.json` por worker. No se guardan credenciales,
no se registra ninguna cuenta ni se automatiza un inicio de sesion.

Este es un control **heuristico de UI**: Perfil puede estar presente en un feed
invitado, y un modal puede ocultarlo en una sesion valida. No certifica autenticacion
en el servidor. Validar los IDs/etiquetas en la version instalada y revisar los
casos pendientes manualmente antes de declarar una placa lista para produccion.

## Smoke test fisico de un subset fijo

```powershell
# Revisar seleccion, sin iniciar workers ni cambiar telefonos.
.\.venv\Scripts\python.exe main.py --smoke-test 3 --activity com.ss.android.ugc.aweme.main.MainActivity --plan

# Una iteracion de video por cada una de las tres placas elegidas.
.\.venv\Scripts\python.exe main.py --smoke-test 3 --activity com.ss.android.ugc.aweme.main.MainActivity --cycles 1
```

`--smoke-test N` implica `--start-farm`, acepta 140 y limita la concurrencia a
`min(--devices,N)`. Admite USB y rutas TCP de Panda verificadas en vivo.
Selecciona una sola vez los primeros N seriales fisicos autorizados
ordenados; excluye los seriales de emulador conocidos y el worker rechaza
`ro.kernel.qemu=1` antes de modificar red. Es una comprobacion practica, no una
prueba criptografica de hardware fisico. Si hay menos de N candidatos, falla
antes de iniciar procesos. No sustituye una placa por otra que aparezca despues.
Las placas ajenas al subset solo se observan en el inventario: no reciben proxy,
firewall, force-stop ni gestos. El dashboard las etiqueta como pasivas durante
la ejecucion. `--cycles 0` no esta permitido en smoke; el valor predeterminado
de ciclos sigue siendo 10, por lo que se recomienda `--cycles 1` para la primera prueba.

Cada worker conserva su origen `-H/-P`, reserva su proxy y activa el firewall antes
de comprobar la salida HTTPS mediante curl Android. La consulta usa
`https://api.ipify.org`, proxy explicito, TLS verificado y sin fallback directo.
Registra en SQLite el resultado observado y despues confirma la IP. Hay exclusion
transaccional sobre las reservas activas y un indice parcial unico por ejecucion
smoke/IP confirmada. Una IP compartida o inesperada deja un registro rechazado,
emite un evento CRITICAL, cancela el arranque de esa app y solicita parar el test.
Los demas workers reciben la senal y cierran cooperativamente; una llamada ADB/API
en curso debe terminar o agotar su timeout antes del cierre.

Las reservas de los workers ya terminados se conservan como `retenido_smoke`
hasta cerrar toda la prueba. Esto impide reutilizar el mismo proxy/IP dentro de
ese smoke test, aunque algunos procesos terminen antes que otros. Se necesitan
N salidas unicas para completar el subset: con menos recursos, las placas restantes
esperan y se muestra la alerta de capacidad. Nunca se reasigna una reserva en
cuarentena ni se limpia una placa fuera del subset. La recuperacion final usa
solo las rutas y leases de los procesos efectivamente iniciados.

La pestana Panel de Control anade **Smoke Test  Logs Vivos**, con refresco cada
segundo, seriales seleccionados, estado de ejecucion, IPs y eventos por worker:
`Espera Dinamica`, `Micro-dumps de interfaz`, carga lenta, red y limpieza. Las
tablas `ejecuciones_granja`, `logs_granja` y `verificaciones_red` conservan esos
datos en WAL incluso al terminar la prueba. Cada micro-dump registra su intento
antes de ejecutarlo; una llamada bloqueada se refleja al retornar o vencer su timeout.
La salida de archivo `worker.log` tambien se escribe con line buffering.

Ctrl+C mantiene la limpieza existente: detener app, retirar cadenas propias,
restablecer proxy y liberar la reserva solo tras verificar la recuperacion. Un
canal inaccesible puede impedir limpiar inmediatamente; se conservan leases y
cuarentenas para recuperar al reconectar. La IP de curl no certifica ausencia de
fugas DNS, todo el trafico de TikTok o reproduccion efectiva. Esta implementacion
no equivale a una prueba fisica ya aprobada: requiere proxies reales, root, IME
preparado y los marcadores de UI correctos en las placas seleccionadas.

## Etapa 4: pool de servidores y arranque de granja ADB

```powershell
# Inventario consolidado; no abre apps, no cambia red ni consulta OpenAI.
.\.venv\Scripts\python.exe main.py --devices 40 --activity com.ss.android.ugc.aweme.main.MainActivity --start-farm --plan

# Iniciar el trabajo en las placas descubiertas, hasta 40 simultaneas.
.\.venv\Scripts\python.exe main.py --devices 40 --activity com.ss.android.ugc.aweme.main.MainActivity --start-farm
```

El descubrimiento real en este host encontro servidores locales en **5037 y 5038**.
Se incluyen ambos en `config/adb_servers.json`. La consulta inicial consolido
**34 seriales unicos autorizados**, sin forzar un conteo de 40. El inventario puede
cambiar con la conexion, autorizacion y configuracion de Panda.

```json
{
  "servers": [
    {"host": "127.0.0.1", "port": 5037},
    {"host": "127.0.0.1", "port": 5038}
  ]
}
```

Agregar unicamente servidores conocidos del laboratorio. No se escanea la LAN
ni se abren puertos para acceso publico. `--adb-servers RUTA.json` permite otra
configuracion; `ADB_SERVERS_CONFIG` define una ruta por entorno. La configuracion
elegida se persiste en SQLite para que el dashboard utilice los mismos origenes,
incluso si ya estaba abierto. No confundir los puertos de servidor ADB (5037/5038)
con el puerto de transporte de un telefono (por ejemplo 5555) o el puerto de proxy.

`core/adb_pool.py` consulta en paralelo `adb -H HOST -P PUERTO devices -l` y unifica
por serial exacto. Preserva todos los origenes de un duplicado; elige el primer
origen autorizado segun el orden de configuracion. Si aparece offline en un
servidor y autorizado en otro, prefiere el segundo. La deduplicacion por serial
no detecta dos identificadores diferentes que correspondan al mismo hardware:
configurar Panda sin aliases de transporte para la misma placa en el inventario.

Antes de invocar adb se comprueba que cada servidor este escuchando; no se pide
arrancar servidores secundarios inexistentes. El codigo no ejecuta `kill-server`,
no crea servidores de Panda y no cambia su configuracion. Usar un cliente ADB
compatible con los servidores instalados: el cliente oficial puede renegociar
un daemon si detecta una incompatibilidad de version de protocolo.

`core/mass_orchestrator.py` usa `multiprocessing.Process` con `spawn`, uno por
serial y un maximo simultaneo dado por `--devices` (140). Si se descubren mas
dispositivos, los restantes esperan turno; si hay menos, arranca los disponibles.
`--stagger 2` escalona arranques sin bloquear el bucle del supervisor. Nuevos
seriales que aparezcan durante la ejecucion se encolan si tienen un proxy disponible.
No se cambia de origen un worker ya activo ni se relanza un worker fallido.

Para `--start-farm`, preparar `config/proxy_pool.json` (o `--proxy-pool RUTA`)
siguiendo `config/proxy_pool.example.json`. El archivo inicial esta vacio: no se
inventan proxies. No se admiten hostname, credenciales ni IPv6 en este modo de
aislamiento. La API key es obligatoria. Si faltan proxies, las placas excedentes
quedan en `Espera - Sin Proxy`; el supervisor permanece activo y Streamlit muestra
**Falta de recursos de red**. El firewall requiere root, iptables, ip6tables y curl HTTPS.

```json
{
  "proxies": [
    {"host":"192.0.2.20","port":8000,"exit_ip":"203.0.113.20","enabled":true}
  ]
}
```

Reemplazar los valores de documentacion por los del proveedor. `exit_ip` es opcional
y representa la salida publica esperada, no la direccion de entrada del proxy.
Se rechazan endpoints repetidos y no se reservan simultaneamente dos endpoints
con la misma salida conocida. Se importa el pool a SQLite y se asigna justo antes
de iniciar cada proceso, bajo `BEGIN IMMEDIATE`, con unicidad por endpoint, identidad
de salida y dispositivo. Los workers comprueban la propiedad de la reserva.
Antes de abrir TikTok, la salida observada por curl se vincula transaccionalmente:
si otro worker ya la reservo o no coincide con la esperada, se cancela el arranque
y se aplica la politica de parada segura. Esto detecta colisiones iniciales, pero
no garantiza IP estable si el proveedor movil rota la salida despues; usar sesiones sticky.

Los proxies se liberan unicamente tras confirmar la limpieza. Si se pierde gestion
o falla la recuperacion, la reserva queda en `cuarentena` y no se reasigna por timeout.
Despues de un cierre abrupto, revisar los leases y recuperar el telefono antes
de liberar manualmente su reserva mediante `ProxyAllocator.finalizar(..., cleanup_ok=True)`.
No borrar reservas para evadir un fallo de limpieza. Las reservas y cuarentenas
se muestran en Configuracion y Pruebas. Los cambios validos del archivo se recargan
cada cinco segundos; no revocan una reserva activa. Escribir el JSON de forma atomica.
El antiguo `--proxies` TXT se mantiene para el modo Appium sin `--start-farm`.

Los arranques usan hasta **40 workers en paralelo**, limitados por `--devices` y
los proxies disponibles. `--bootstrap-parallelism 1` conserva el escalonado de
25 segundos. La admision API usa SQLite para conservar el limite RPM y de
concurrencia sin semaforos que puedan quedar bloqueados al terminar un proceso.
TPM, reintentos y otros consumidores tambien afectan los limites del proveedor.

Cada video usa `esperar_feed` en `core/selectors.py` antes de consultar IA: hasta
cinco micro-dumps comprimidos, sin PNG/pull, con presupuesto de quince segundos.
Busca un contenedor visible del paquete esperado. `--feed-markers RUTA.json`
acepta `{"markers":["id_real_del_reproductor","id_real_del_feed"]}` para la version
instalada. Los valores por defecto son heuristicos; mapear los IDs ofuscados en la
placa real antes de la ejecucion masiva. Una pestana con texto Para Ti no basta.

Tras quince segundos sin contenedor se registra `Carga Lenta - Reintentando`,
visible en el inventario y conservado en el historial SQLite/Streamlit. Se permiten
`--max-failures` ventanas antes de detener el worker. Los sondeos son interrumpibles;
`--start-farm` sustituye las esperas fijas de carga por este callback en cada video.
La presencia del contenedor no acredita decodificacion, reproduccion ni cambio
atomico al siguiente video. Las pausas de retencion siguen siendo duracion de prueba,
no esperas para decidir que cargo la UI.

Cada worker fija su servidor con un contexto local al proceso/hilo: los comandos
de proxy, shell, UI dump, Unicode, gestos y limpieza reciben siempre `-H/-P` del
origen correspondiente. Se eliminan variables `ADB_SERVER_SOCKET` y equivalentes
del entorno de esos comandos para evitar que redirijan la sesion a otro servidor.
Cada worker tiene su propio directorio y cliente OpenAI. `--api-concurrency` y
`--rpm` limitan globalmente las consultas de todos los workers; los reintentos
internos del SDK pueden anadir peticiones a la cuota, como en los otros modos.

El firewall permite TCP hacia el proxy, rechaza otra salida IPv4/IPv6 y preserva
respuestas adbd ESTABLISHED desde el puerto de transporte hacia los peers de
gestion observados con `ss -tn`/`netstat -tn`. **No se anade una excepcion global
ESTABLISHED** que deje pasar conexiones existentes de TikTok. En transporte TCP,
si no se identifica el canal de gestion, no se instala el firewall ni se abre la app.
Se verifica la IP con curl bajo las restricciones antes del arranque. Las reglas
bloquean bypass; no convierten una app que ignore el proxy en una app compatible.
Su alcance sigue siendo OUTPUT del kernel: no acredita ausencia de fugas por
mecanismos OEM/offload ni que el video se reproduzca correctamente.

`--cycles 10` procesa diez videos por placa; `--cycles 0` mantiene lotes hasta
Ctrl+C. `--start-farm` aplica las decisiones mediante ADB, sin necesitar Appium ni
`--execute`. El modo anterior sin ese flag conserva Appium y su propia logica;
tambien recibe ahora el origen ADB en `remoteAdbHost`/`adbPort`.

El supervisor consulta el pool y actualiza SQLite cada cinco segundos nominales
(sujeto a latencia/timeouts). El dashboard usa el mismo pool. Un servidor que falla
queda registrado con su error; las placas cuya presencia no se pudo verificar
se marcan `servidor_no_disponible`, distinto de una ausencia observada en un
servidor que si respondio. El conteo representa dispositivos actualmente
confirmados, no una capacidad objetivo ni el ultimo valor inflado.

Ctrl+C/SIGTERM solicitan parada cooperativa; los workers detienen la app antes de
retirar firewall y proxy de su propio servidor. Un worker abortado se recupera
de forma aislada, con watchdog, reconexion y reintentos acotados. No se matan los
servidores ADB compartidos de Panda. `--shutdown-grace 180` acota la espera antes
de terminar workers que no respondan y ejecutar recuperacion desde el supervisor.

Se persisten `proxy_lease.json` y `firewall_lease.json` antes de las mutaciones.
La recuperacion solo elimina cadenas con nombre de este worker; nunca hace flush
de OUTPUT ni de reglas ajenas. Los artefactos estan en `sessions/farm/<run_id>/`:
manifest, inventario, bitacoras, decisiones y resumen de cierre. Si USB/red/servidor
siguen inaccesibles, la limpieza inmediata es imposible: quedan
`cleanup_required.json` y los leases con origen preciso para recuperar al reconectar.
No se afirma validacion fisica del firewall ni certificacion de produccion con
40 placas: las pruebas de red masiva en este cambio son de descubrimiento y las
pruebas de ejecucion usan dobles para no modificar las placas reales.

[Opciones oficiales ADB -H/-P](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/user/adb.1.md).

## Dashboard y persistencia SQLite

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --ui
```

Abrir [dashboard local](http://127.0.0.1:8501). El flag inicia Streamlit como
subproceso usando el mismo Python y una ruta absoluta; funciona sin ADB/API key.
Escucha exclusivamente en loopback y no solicita email en su primer inicio.
Detener con Ctrl+C en la terminal que ejecuta el servidor.

Acceso de escritorio: **Panda Box QA.lnk** ejecuta `launch_dashboard.py` con
`pythonw.exe`. Abre el dashboard existente o inicia Streamlit sin consola y espera
su endpoint de salud antes de abrir el navegador. Un bloqueo local evita dos
arranques simultaneos. El registro esta en `sessions/dashboard-server.log`.
Para comprobar el arranque sin abrir otra pestana:

```powershell
.\.venv\Scripts\python.exe launch_dashboard.py --no-browser
```

- **Panel de Control:** inventario ADB real refrescado cada cinco segundos,
  conectado/ultima conexion, alias, proxy, estado y heartbeat. Verde Calentando,
  amarillo Espera, rojo Error y gris Desconectado. No se inventan registros para
  completar 40 placas. Si falla ADB, se conserva la ultima lectura y se advierte
  que el conteo de conexiones no pudo verificarse.
- **Auditoria de IA:** pagina de 25 registros, orden mas reciente primero y filtros
  por dispositivo o SKIP valido. Los errores de API con decision fallback no se
  presentan como SKIP de OpenAI. Los timestamps se almacenan en UTC; los KPIs de
  hoy usan America/Guatemala (UTC6).
- **Configuracion y Pruebas:** boton para iniciar `--test-device --diagnose-device`
  en un subproceso sin ventana de consola. Cada ejecucion tiene directorio propio
  en `sessions/diagnostics_ui/<id>`. Las preguntas del operador se responden en la
  web; la imagen y el JSON se muestran dentro del dashboard. Las preguntas expiran
  tras diez minutos. Cancelar solicita salida cooperativa y restauracion del IME;
  durante un comando ADB hay que esperar su timeout. Solo se permite un diagnostico
  simultaneo por servidor Streamlit. Cerrar una pestana no mata el proceso.

`core/database.py` crea `data/granja_tiktok.db` con las tablas `dispositivos` e
`interacciones`, claves foraneas e indices de fecha/dispositivo. Se usa SQLite WAL,
`busy_timeout=15000` y una conexion por operacion, cerrada al terminar la transaccion.
No se comparten conexiones entre hilos ni procesos: no es necesario desactivar
`check_same_thread`. Los escritores se serializan en transacciones cortas; una
lectura de UI no mantiene bloqueada una conexion durante una llamada API o espera.

Para ubicar la base en otro directorio local, definir `TIKTOK_DB_PATH` con una ruta
absoluta **antes de iniciar ambos procesos**, backend y dashboard. WAL se destina a
procesos del mismo host sobre disco local, no a una base compartida por red o
sincronizacion de archivos en vivo. Fuera de la raiz operativa, OneDrive puede usarse una
ruta local fuera de la carpeta sincronizada. No se suben bases ni sesiones a Git.

Ambos flujos IA (ADB individual y workers Appium) mantienen JSONL y escriben la
decision en SQLite antes de ejecutar acciones. Un registro comienza `pendiente`,
se actualiza al recibir los eventos de clic y finaliza `completada` o `error`.
La clave unica `(run_id,id_adb,ciclo)` evita duplicar un registro reinsertado; no
constituye una garantia de exactly-once de acciones externas. Un corte forzado
puede dejar un registro pendiente, que queda visible para revision.

Las columnas adicionales `ia_valida`, `estado`, `error`, `run_id` y `ciclo`
permiten separar intentos, decisiones validas y ciclos incompletos. `latencia_ms`
es el tiempo de consulta IA, incluidos reintentos del SDK. `dio_like` y `comento`
indican clics ejecutados y confirmados por ADB/Appium, no aceptacion por el servidor
de TikTok; `comentario_texto` solo se rellena al pulsar enviar. Las decisiones
solicitadas se conservan completas en `decision_ia`.

Los KPIs de exito cuentan ciclos completados con IA valida hoy. Cada tasa es
clics de ese tipo / esos ciclos, incluyendo SKIP en el denominador. La auditoria
permite inspeccionar tambien errores, pendientes y decisiones que no llegaron a
producir acciones. SQLite no reemplaza el registro de recuperacion de firewall/IME.

Referencias: [fragmentos Streamlit](https://docs.streamlit.io/develop/concepts/architecture/fragments),
[conexiones sqlite3](https://docs.python.org/3/library/sqlite3.html).

Python 3.11+, procesos `spawn` independientes y un servidor Appium local por
placa. El valor predeterminado es 20; `--devices 40` utiliza 40. Los dispositivos
se descubren con `adb devices`, se filtran por estado `device` y se ordenan por
UDID. Cada ejecucion conserva el mapeo en los eventos `start` por dispositivo.

| Recurso | Para 40 placas |
|---|---|
| Appium | 47234762, solo loopback |
| UiAutomator2 systemPort | 82008239 |
| MJPEG | 92009239 |
| Proxy | uno distinto por placa |

## Preparacion

Instalar Android Platform Tools y exponer `adb` en PATH (o definir `ADB_PATH`).
Tambien se detecta automaticamente `tools/platform-tools/adb.exe` dentro del
proyecto, `ANDROID_HOME`, `ANDROID_SDK_ROOT` y el SDK estandar de Android Studio
en `%LOCALAPPDATA%/Android/Sdk`. `ADB_PATH` explicito tiene prioridad; si es
invalido, se informa para corregirlo. La instalacion local de herramientas se
excluye de Git y permite al dashboard encontrar ADB sin cambiar el PATH de Windows.
Instalar Node.js, Appium y el driver UiAutomator2 compatibles con el Android
de las placas. Autorizar depuracion USB en cada dispositivo. Requiere TikTok
instalado y una sesion iniciada; `noReset=True` conserva los datos existentes,
pero no garantiza que una sesion siga siendo valida.

```powershell
npm install -g appium
appium driver install uiautomator2
appium driver doctor uiautomator2
adb devices
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config/proxies.example.txt config/proxies.txt
Copy-Item config/selectors.example.json config/selectors.json
$env:OPENAI_API_KEY = 'tu-clave'
```

Completar `config/proxies.txt` con hasta 40 entradas unicas `hostname:puerto`,
sin esquema ni credenciales. Usar proxies que admitan allowlist de IP si
requieren autorizacion. La asignacion usa el mismo orden de la lista y de los
UDID ordenados. Para inventarios cambiantes, revisar siempre `--plan`.

Obtener el paquete/activity real de la version instalada, por ejemplo con
`adb -s UDID shell cmd package resolve-activity --brief com.zhiliaoapp.musically`.
El perfil global usa por defecto `com.ss.android.ugc.aweme.main.MainActivity`; cada worker comprueba que el componente exista antes de modificar red o abrir la app.
El paquete tambien se puede cambiar con `--package`.

El paquete predeterminado es `com.zhiliaoapp.musically`, confirmado en AGX.
El perfil esta en `config/tiktok_app.json`. `--activity` acepta la clase o el
componente completo; el paquete a la izquierda de `/` debe coincidir con
`--package`. El namespace `com.ss.android.ugc.aweme.main.MainActivity` es una
clase valida del perfil global y no cambia el paquete APK. Su existencia se
resuelve en la placa antes del arranque.

```powershell
# Validacion de inventario, proxies y puertos; sin cambios en las placas.
.\.venv\Scripts\python.exe main.py --devices 40 --activity ACTIVITY_REAL --plan

# Auditar 10 pantallas por placa, consultando IA y haciendo swipe.
.\.venv\Scripts\python.exe main.py --devices 40 --activity ACTIVITY_REAL --cycles 10

# Aplicar las decisiones: requiere selectores verificados de la version instalada.
.\.venv\Scripts\python.exe main.py --devices 40 --activity ACTIVITY_REAL --cycles 0 --execute
```

Los XPath de `config/selectors.json` deben verificarse con Appium Inspector:
`like`, `comments`, `comment_input`, `comment_send`, `comment_close`. El XPath
de like debe seleccionar unicamente un boton aun no seleccionado; de lo contrario
un clic puede retirar un like existente. La IA nunca elige selectores. El cierre
del panel de comentarios debe devolver al feed. Probar primero una placa, luego
incrementar a 5, 20 y 40; no se ha certificado rendimiento en hardware Panda Box.

## Ejecucion, fallos y auditoria

### Prueba de red en un unico dispositivo USB

La prueba de red y `--map-only` no requieren Appium en ejecucion, API key ni archivo de proxies. La Etapa 3 si requiere OPENAI_API_KEY. Selecciona
la primera entrada `device` con propiedad `usb:` de `adb devices -l`. Si falta
ADB muestra instrucciones para instalar Platform-Tools; no usa ppadb porque este
cliente tambien necesita un servidor ADB operativo para gestionar USB.

```powershell
$env:ADB_PATH = 'C:\Android\platform-tools\adb.exe'
.\.venv\Scripts\python.exe main.py --test-device --proxy proxy.example.com:8080 --expected-exit-ip 203.0.113.10

# Etapa 2: proxy con IPv4 literal, dispositivo root, aislamiento y captura de UI.
.\.venv\Scripts\python.exe main.py --test-device --proxy 192.0.2.20:8080 --expected-exit-ip 203.0.113.10 --open-tiktok --activity com.ss.android.ugc.aweme.main.MainActivity --map-only

# Solo mapear la pantalla ya visible, sin abrir la app ni aplicar firewall.
.\.venv\Scripts\python.exe main.py --test-device --proxy proxy.example.com:8080 --expected-exit-ip 203.0.113.10 --activity ACTIVITY_REAL --map-only
```

Reemplazar los valores de ejemplo. `--expected-exit-ip` es la IP **de salida**
indicada por el proveedor, que puede ser distinta de la IP de entrada del proxy.
Para proxies rotativos se necesita una salida fijada durante esta prueba.

El test escribe y verifica `settings put global http_proxy` **en Android**. Luego
ejecuta el `curl` instalado en el telefono hacia `https://api.ipify.org` con
proxy HTTP explicito, TLS verificado, sin bypass por `NO_PROXY` ni fallback directo.
No instala curl automaticamente: si falta o no soporta HTTPS, termina con error y
limpia el ajuste. No modifica el proxy de Windows.

La coincidencia confirma unicamente la salida HTTPS de esa peticion curl. **No es
una prueba de fugas DNS ni acredita el enrutamiento de TikTok**: el ajuste Android
puede ser ignorado por aplicaciones. Una garantia para todas las conexiones requiere
VPN/firewall/gateway y medicion independiente de trafico/DNS. No se afirma esa
garantia con este modo.

La prueba de red sin activity limpia al terminar la peticion. `--map-only` captura
la pantalla visible; combinado con `--open-tiktok` abre la app y conserva el proxy
hasta Ctrl+C. El ciclo de Etapa 3 limpia al completar los videos o al interrumpirlo.
Comprueba periodicamente la conexion ADB y reglas del firewall. `finally` intenta limpiar
tambien ante errores, Ctrl+C y SIGTERM, con tres intentos; si fallan muestra el
comando manual. Apagado electrico, `TerminateProcess` o USB desconectado impiden
garantizar una limpieza inmediata. Se restablece a `:0`, no al proxy anterior.

### Etapa 2: aislamiento y mapeo de UI

`--test-device --open-tiktok` requiere root (adbd root o `su -c`), `iptables`,
`ip6tables` y una **IPv4 literal** del proxy. No se rootea el dispositivo.
Se detiene la app, se crean cadenas temporales propias y se insertan al principio
de OUTPUT. IPv4 solo permite TCP hacia IP:puerto del proxy y rechaza el resto;
IPv6 se rechaza por completo. Esto afecta a **todo el dispositivo de prueba**,
incluido DNS, QUIC, otras apps y ADB por red; usar exclusivamente USB.
Los nombres DNS de destinos HTTPS se envian en CONNECT al proxy de curl.

Una app que ignore `http_proxy` puede quedarse sin red: las reglas bloquean bypass,
no implementan traduccion transparente de TCP/UDP hacia HTTP. No existe un ajuste
ADB universal para deshabilitar QUIC de cualquier app. No se garantiza cobertura
de mecanismos de red propietarios/OEM, offload o trafico fuera de OUTPUT; confirmar
en un gateway externo antes de afirmar ausencia total de fugas.

Antes del arranque se vuelve a consultar ipify bajo las restricciones. Sin root,
si falla cualquiera de las dos familias o no coincide la IP, **no se inicia la app**.
`sessions/netpolicy.txt` se guarda como diagnostico; su contenido por si solo no
acredita aislamiento. Como alternativa administrada puede usarse una VPN always-on
con lockdown, que este modulo no configura ni valida automaticamente.

El arranque por defecto hace `am force-stop com.zhiliaoapp.musically`, seguido de
`am start -W -n com.zhiliaoapp.musically/com.ss.android.ugc.aweme.main.MainActivity`.
`-n` elige componente; force-stop provoca el arranque nuevo sin borrar sesiones.
`--activity` acepta el componente real instalado, no el texto literal ACTIVITY_REAL
cuando tambien se solicita abrir la app. Con `--open-tiktok` se usa la activity
Aweme indicada arriba si se omite `--activity`.

Se ejecuta `uiautomator dump /sdcard/window_dump.xml` y `adb pull` hacia
`sessions/window_dump.xml`, ademas de una captura PNG opcional. El parser de
`core/selectors.py` usa `xml.etree.ElementTree`, rechaza entidades/DOCTYPE y limita
el tamano de entrada. Guarda `sessions/components.json` con:

- Candidatos de descripcion, like y comentarios por texto, accessibility y resource-id.
- Todos los nodos pulsables con `bounds`, centro en pixeles y centro normalizado.
- Componentes textuales para inspeccionar IDs ofuscados sin asignarles significado inventado.

Son candidatos heuristicos: verificar que la pantalla sea realmente Para Ti y no
un modal, login u otra seccion. No se generan selectores definitivos automaticamente.
`--test-device --map-only --activity ACTIVITY_REAL` captura la pantalla **ya visible** tras la
prueba de IP; con `--open-tiktok --map-only` captura despues de arrancar bajo el firewall.
Este flujo nuevo se limita a una placa; el orquestador de 40 placas conserva su
comportamiento previo y no instala este firewall.

Ctrl+C detiene la app antes de retirar las cadenas propias y limpiar el proxy.
No se hace flush de OUTPUT ni se eliminan reglas ajenas. Antes de modificar reglas
se persiste `sessions/firewall_cleanup_required.txt` con comandos root de recuperacion;
se elimina al completar la limpieza. `sessions/network_guard.json` registra el
alcance configurado durante la prueba. Los archivos de UI pueden incluir datos
personales y se excluyen de Git mediante `.gitignore`.

### Etapa 3: ciclo IA y acciones ADB en una placa

```powershell
$env:OPENAI_API_KEY = 'tu-clave'
.\.venv\Scripts\python.exe main.py --test-device `
  --proxy 192.0.2.20:8080 --expected-exit-ip 203.0.113.10 `
  --activity com.ss.android.ugc.aweme.main.MainActivity --ai-videos 5
```

Reemplazar las IP de ejemplo por valores reales. Con `--test-device`, una activity
real activa el arranque protegido y el ciclo IA/ADB; `--open-tiktok` tambien lo
activa usando la activity predeterminada si se omite. `--map-only` conserva la
Etapa 2 sin decisiones ni acciones IA. El ciclo individual aplica las decisiones
por defecto; el flag `--execute` pertenece al orquestador Appium y no controla
este modo. La prueba admite 120 videos, con 5 por defecto.

`core/ai_orchestrator.py` vuelve a capturar y leer `sessions/components.json` en
cada ciclo. Prioriza la descripcion, despues hashtags y finalmente textos de
componentes pulsables en la zona inferior izquierda. Intenta hasta tres lecturas
si no hay contexto. La IA interpreta exclusivamente ese texto, no imagenes/audio.
La clasificacion de spam, bots y odio se exige en el prompt y no es una garantia
determinista; contexto vacio fuerza localmente la ausencia de interacciones.

Se usa `gpt-4o-mini` con `response_format={"type":"json_object"}` y Pydantic estricto:

```json
{
  "interactuar": true,
  "dar_like": true,
  "comentar": true,
  "comentario_texto": "que buen video",
  "tiempo_retencion_segundos": 18
}
```

JSON mode valida sintaxis en la API; los campos, tipos, 1228 segundos, coherencia,
minusculas y maximo de ocho palabras se validan localmente. El host sortea el
entero de espera y lo fija en la decision efectiva: el modelo no proporciona una
fuente de aleatoriedad fiable. Una respuesta invalida, truncada, rechazada o un
fallo de API produce una decision sin acciones y se avanza. No hay llamadas API
en las pruebas locales.

La espera se divide en pasos de un segundo para comprobar USB/firewall y permitir
Ctrl+C. Despues se recaptura la UI: si cambio el contexto, se omiten interacciones.
Los toques requieren un unico candidato del paquete esperado, habilitado y con
coordenadas validas; los likes marcados como seleccionados se omiten. La deteccion
heuristica requiere validacion en el dispositivo, especialmente si TikTok no
expone el estado seleccionado.

Para comentarios Unicode se necesita **ADBKeyBoard previamente instalado** en la
placa de prueba, con componente `com.android.adbkeyboard/.AdbIME`. No se descargan
ni instalan APK automaticamente. Revisar y preparar ese IME desde su
[repositorio oficial](https://github.com/senzhk/ADBKeyBoard). El framework habilita
y activa temporalmente el IME; envia el texto UTF-8 codificado en Base64 usando
`am broadcast -a ADB_INPUT_B64 -p com.android.adbkeyboard --es msg ...`. Nunca
concatena texto del modelo en un comando shell ni usa `input text` para Unicode.

Antes de enviar se comprueba que el editor exponga exactamente el texto escrito
y que exista un unico boton de envio. Si falta el IME o hay un borrador, se omite
el comentario; si falla la verificacion despues de escribir, se detiene la prueba
para revisar el borrador. El teclado anterior y su estado se restauran en `finally`;
`sessions/ime_cleanup_required.txt` permite recuperacion si se pierde USB.

Despues del comentario se cierra teclado/panel y se verifica el regreso al mismo
contexto antes del swipe. El swipe usa `adb shell input swipe` con variacion de
15 pixeles y duracion de 400650 ms. Las variaciones cubren coordenadas de prueba;
no acreditan comportamiento humano, reproduccion efectiva ni retencion contabilizada.
Un error de gesto o resultado ambiguo detiene el ciclo sin repetir publicaciones.

`sessions/audit.jsonl` registra run_id, UDID, ciclo, decision, hash/fuente del
contexto, intentos y clics, omisiones, swipe y cierre/aborto. Se conserva un reporte
por video en `<run_id>-video-NN.json`; `components.json` y las capturas son la
ultima lectura. Un clic en enviar no confirma aceptacion del comentario por el
servidor. Finalizados los videos se detiene la app y se retiran firewall y proxy.

`--cycles 0` mantiene el ciclo hasta Ctrl+C. `--stagger 2` escalona arranques.
`--api-concurrency 4` limita consultas simultaneas y `--rpm 30` limita globalmente
inicios de consulta; los reintentos internos del SDK tambien consumen cuota.
Cada proceso reutiliza su cliente OpenAI. `--interval 3` separa ciclos.
El maximo real depende de cuotas TPM/RPM y del tamano del arbol UI.

Los fallos de USB, lectura UI o API cierran la sesion y reintentan con backoff
acotado. Cinco fallos consecutivos detienen el worker y solicitan parar al resto.
Un resultado ambiguo al pulsar/enviar detiene la ejecucion para evitar repetir
automaticamente esa operacion. No existe garantia de exactly-once ni de que
un clic equivalga a una publicacion aceptada por el servidor; validar esas
postcondiciones requiere aserciones especificas de la aplicacion.

`runs/<UTC>/device-NN.jsonl` contiene UDID, ciclos, decisiones, hash del contexto,
trayectorias y resultados de limpieza. Los logs Appium quedan en el mismo
directorio y pueden contener datos de UI; proteger y retener segun el entorno.
La auditoria registra configuracion del proxy, no captura paquetes ni acredita
la IP de salida. El XML se filtra a etiquetas accesibles, se acota y se envia a
OpenAI; revisar esos datos antes de ejecutar con cuentas de prueba.

El supervisor espera hasta 120 segundos para cierre cooperativo. Los `finally`
cierran driver/servidor y limpian el proxy; el supervisor vuelve a intentar
la limpieza. Si el dispositivo esta desconectado, se registra `cleanup_required`.
Al reconectarlo, ejecutar:

```powershell
adb -s UDID shell settings put global http_proxy :0
```

Un cierre forzado del sistema o del worker puede dejar procesos Appium hijos;
comprobarlos antes de otra ejecucion. La comprobacion previa de puertos detecta
ocupaciones existentes, pero no reserva los puertos durante toda la ejecucion.

## Limites tecnicos

- `settings put global http_proxy` configura un proxy HTTP del SO: no es una VPN,
  no cambia hardware y las aplicaciones pueden ignorarlo. No garantiza cobertura
  de QUIC/UDP ni todo el trafico TikTok. Verificar red con instrumentacion externa.
- Los gestos usan coordenadas de pantalla y curvas suaves W3C. No reproducen
  presion, friccion fisica ni garantizan equivalencia con un dedo real.
- El modelo analiza texto accesible, no imagenes ni audio del video. La respuesta
  usa JSON Schema estricto y validacion local de booleanos, minusculas y 8 palabras.
- La relectura UI antes de actuar reduce decisiones sobre contenido cambiado,
  pero no es atomica y los contadores dinamicos pueden causar omisiones.
- Una placa bloqueada, un dialogo, CAPTCHA o perdida de sesion requiere resolver
  el estado de prueba; no hay un flujo que los eluda.
- 40 procesos no equivalen a capacidad fisica garantizada. Medir CPU/RAM,
  estabilidad de controladores USB, alimentacion de hubs y tiempos UiAutomator2.

## Pruebas

### Diagnostico interactivo fisico, sin creditos OpenAI

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --test-device --diagnose-device
```

Requiere ADB, una placa USB autorizada, TikTok visible y ADBKeyBoard instalado.
No requiere `OPENAI_API_KEY`, proxy, Appium en ejecucion ni root. Para otra variante
usar `--package com.zhiliaoapp.musically`. No combina con flags de arranque o
configuracion de proxy: observa el estado de red ya preparado y registra el valor
actual de `http_proxy`; no instala ni retira restricciones de red.

El asistente de consola guia estos pasos:

1. Dejar Para Ti visible. Se recaptura `components.json` y la pantalla real en
   `sessions/current_screen.png`. Pillow genera `sessions/debug_layout.png` con
   rectangulos rojos semitransparentes, cruces amarillas en los centros y coordenadas.
   En Windows se abre el visor de imagenes. Confirmar visualmente con `s` o `n`.
   Se rechaza una diferencia de tamano/orientacion entre screenshot y mapa. XML y
   screenshot son capturas sucesivas, no atomicas; mantener quieta la interfaz.
2. Se abre Ajustes mediante `am start -W -a android.settings.SETTINGS`. Abrir su
   buscador, vaciarlo y enfocarlo manualmente antes de continuar por consola.
   Se usa esta actividad neutral porque no existe un editor generico universal
   para todos los fabricantes. No se crean contactos ni se envian comentarios.
3. El IME se activa temporalmente; el diagnostico envia exactamente
   `hola, probando automatizacion de granja 2026! ` mediante Base64/UTF-8 y realiza
   un dump inmediato. Verifica el texto completo en un EditText XML, no solo el
   resultado del broadcast. Si no coincide, muestra una alerta de configuracion
   de ADBKeyBoard/foco/accesibilidad. Se envia `ADB_CLEAR_TEXT` para borrar la busqueda
   y se restaura el teclado anterior incluso ante Ctrl+C. Si se pierde USB puede
   quedar texto en la busqueda; revisar el telefono y el archivo de recuperacion IME.
4. Regresar manualmente a TikTok y continuar por consola. Durante 1228 segundos
   se recoge `dumpsys gfxinfo PAQUETE framestats` cada tres segundos, sin imprimir
   su salida. Se guardan contadores, diferencias entre muestras y latencia ADB.

Artefactos: `sessions/diagnostics.json`, `sessions/keyboard/window_dump.xml`,
`sessions/performance/gfxinfo-NN.txt` y `sessions/performance/summary.json`, ademas
de la imagen y mapa del feed. Contienen datos de UI del dispositivo; no se envian
a OpenAI. Las pruebas de regresion verifican que el protocolo no cree un cliente
OpenAI ni necesite una API key.

El informe exige confirmacion visual, los tres tipos de candidatos dibujados,
coincidencia exacta Unicode y muestras de renderizado utiles para marcar `passed`.
El codigo de salida es 0 para ese alcance, 2 si requiere revision y 1 ante errores
de inicializacion/ADB. Ctrl+C interrumpe con 130. No es una certificacion de red,
ni demuestra que un toque publique o de like: no se pulsan esos botones.

`gfxinfo` mide renderizado HWUI y puede omitir SurfaceView/video. Se advierte
posible jank sostenido si al menos tres intervalos tienen diez o mas frames y
un 10% o mas de jank. Es una heuristica de esta ventana, no un umbral oficial
ni una atribucion causal al proxy. Ausencia de contadores o frames suficientes
produce resultado inconcluso; procesos reiniciados pueden alterar los contadores.
La duracion real puede superar la espera solicitada por la latencia de ADB.

[Documentacion de dumpsys/gfxinfo](https://developer.android.com/tools/dumpsys).

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py -v
```

Las pruebas Android usan dobles y validan inventario, 120 puertos sin colisiones,
comandos ADB, JSON, filtrado UI y payload W3C real de Selenium. No necesitan
dispositivos ni llamadas OpenAI. La prueba web conservada usa Chromium instalado.
El framework Playwright anterior se conserva en `web_qa.py` y `core/web_actions.py`.

Referencias: [Structured Outputs de OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs),
[Capabilities UiAutomator2](https://appium.github.io/appium-uiautomator2-driver/latest/reference/capabilities/),
[Platform-Tools oficiales](https://developer.android.com/tools/releases/platform-tools),
[API ipify](https://www.ipify.org/),
[Opciones de proxy de curl](https://curl.se/docs/manpage.html).

### Validacion de campo

Comando global corregido (el perfil por defecto permite omitir `--activity`):

```powershell
.\.venv\Scripts\python.exe main.py --smoke-test 3 --activity com.zhiliaoapp.musically/com.ss.android.ugc.aweme.main.MainActivity --cycles 1
```

El subset usa los alias historicos de AGX por serial fisico; logs y manifiesto
incluyen el UUID canonico, y `interacciones.legacy_device_id` enlaza las nuevas
consultas con ese historial. El alias nunca sustituye al serial en comandos ADB.

Se rescato el inventario e historial privado del proyecto AGX. Consulta
[el informe de recuperacion](docs/agx-recovery.md) para cifras, respaldos,
reimportacion y diferencias de paquete TikTok detectadas.

Para integracion sin SDK ni placas, activar explicitamente `--simulate-env`:

```powershell
.\.venv\Scripts\python.exe main.py --simulate-env --smoke-test 3 --activity com.ss.android.ugc.aweme.main.MainActivity --cycles 1
.\.venv\Scripts\python.exe main.py --simulate-env --ui
```

El doble Panda genera 34 identidades `SIMULADO-*` en `data/simulation.db`, sin
marcarlas como conectadas fisicamente ni registrar autenticacion o latencias
inventadas. No ejecuta ADB, reglas de red ni OpenAI. `.venv` por si solo no activa
la simulacion. El dashboard normal sigue usando la base de produccion.

El smoke fisico asigna los primeros N objetos del JSON, por orden, al subset
ordenado de seriales. Rechaza entradas deshabilitadas y fija las asignaciones
durante la ejecucion. Los procesos publican `Navegando`, `Analizando con IA` y
`Pendiente Cuenta` en WAL; Streamlit los muestra en su siguiente refresco.
Al cerrar, incluso por SIGINT/SIGTERM cooperativo, `resumenes_carga` conserva
muestras, media y maximo por placa. Es tiempo observado de espera de UI mas auth,
no latencia de reproduccion. Sin medicion se guarda null, nunca cero ficticio.
El resumen tambien aparece en la seccion de logs del smoke test.

El comando maestro ejecuta `core/deployment_check.py` antes de tocar Android.
Si `config/proxy_pool.json` falta o esta vacio, crea una plantilla deshabilitada y
detiene el arranque. Sustituir los ejemplos por endpoints residenciales fijos del
proveedor, puerto entero e IP publica de salida esperada; activar `enabled`.
La condicion residencial debe confirmarla el operador con el proveedor.
Se necesitan tres salidas diferentes para el smoke de tres placas.

```powershell
$env:ADB_PATH = 'C:\Android\platform-tools\adb.exe'
.\.venv\Scripts\python.exe main.py --smoke-test 3 --activity com.ss.android.ugc.aweme.main.MainActivity --cycles 1
```

Requiere el binario fisico indicado, `OPENAI_API_KEY`, Panda escuchando en
5037/5038, transporte USB o TCP autorizado, root e iptables/ip6tables. Se conserva el servidor de
origen de cada placa; no se reinician los servidores Panda. El subset queda fijo
y cada worker confirma USB o identidad fisica TCP, descarta emuladores y despierta la pantalla.
El firewall precede al arranque. El login visible registra Pendiente Cuenta en WAL
y la fila amarilla aparece en el siguiente refresco del dashboard. Sin login,
se conserva el chequeo de perfil y el ciclo IA con espera real de 1228 segundos.
La limpieza detiene la app antes de retirar el firewall y liberar el proxy;
una limpieza fallida mantiene la reserva en cuarentena. La UI es una heuristica
de sesion y la espera no certifica reproduccion ni aceptacion del servidor.

### Reconexion TCP y vinculo con AGX

`config/adb_servers.json` referencia `adb_devices.local.json`, un archivo privado
con direcciones de placas por servidor. La instalacion actual conserva 34
direcciones observadas. Ver `config/adb_devices.example.json` para su estructura.
Tambien se admite una lista `devices` dentro de cada objeto de servidor.

Al iniciar granja y en cada sondeo, se consulta primero el servidor existente.
Solo para direcciones configuradas ausentes u offline se ejecuta
`adb -H HOST -P PUERTO connect IP:PUERTO`, seguido de otra lectura de `devices -l`.
El bootstrap puede inicializar un daemon ADB local ausente en su puerto configurado;
no reinicia uno existente ni el proceso Panda. Una placa `unauthorized`
necesita autorizacion del operador; no se intenta eludirla. `--plan` y la lectura
del dashboard no reconectan equipos.

### Arranque de un clic y recuperacion tras apagado

Doble clic en `Iniciar-Granja.cmd`: inicia el backend continuo con hasta 40
workers, usando el perfil TikTok global. La granja de 34 placas no requiere 40
proxies por tener ese limite de concurrencia; cada worker necesita su propio
endpoint disponible. Con recursos incompletos, las restantes esperan.

El bootstrap recupera ADB y el inventario antes de validar las dependencias de
los workers. Un pool vacio o una API key ausente bloquea el lanzamiento de apps,
pero deja registrados los dispositivos que si logro reconectar y la alerta.
No se abre TikTok fuera del firewall para sortear esa falta de configuracion.

Consulta [la operacion del bootstrap](docs/bootstrap.md) para los limites,
la recuperacion de leases y las mediciones. El dashboard se abre con
`.\.venv\Scripts\python.exe main.py --ui`.

Las rutas TCP leen `ro.serialno` y `ro.boot.serialno` y rechazan emuladores,
seriales genericos y discrepancias entre ambas fuentes. El serial fisico enlaza
con AGX por igualdad exacta. Una identidad nueva valida se registra como nueva,
sin inventar sesion o alias historico. Si rutas distintas declaran el mismo
serial fisico, se bloquea la seleccion ambigua para evitar dos workers sobre la
misma identidad.

ADB, firewall y capturas usan la direccion de transporte; SQLite, reservas,
estados y consultas IA usan el serial fisico estable. `adb_transport` permite
ver ambos datos en el panel. Se vuelve a verificar la identidad al arrancar,
durante la ejecucion y antes de limpiar. Si la IP ahora apunta a otra placa,
se cancela la operacion y se conserva la cuarentena cuando haya leases.

Etapa 2: [Activity Manager ADB](https://developer.android.com/tools/adb),
[VPN always-on administrada](https://developer.android.com/work/dpc/network-telephony).
# Cuentas web aisladas y evidencia visual

El binding TCP del host, su instalacion local y los estados de verificacion se
documentan en [Tun2socks del host](docs/TUN2SOCKS_HOST.md). No sustituye al motor
Android pendiente dentro del APK ni desbloquea su despliegue por si solo.

Para el controlador Android VPN Always-on/Lockdown consultar
[Contrato del helper y recuperacion](docs/LOCKDOWN_VPN.md). Este modo requiere un
APK funcional, consentimiento y primera validacion USB. Las fuentes actuales
compilan un helper de control sin motor TCP; no acreditan aislamiento mediante
un unico flag secure. `scripts/compilar_helper.py` genera y verifica el artefacto.

Para instalar este modo en otra PC y operarlo desde Streamlit, seguir
[Instalacion web reproducible](docs/INSTALACION_WEB.md). Incluye preparacion de
`.venv`, Patchright/Chromium, proxies, perfiles persistentes y validacion de
selectores. Ejecutar `python scripts/preparar_web.py --install` en el destino.

El laboratorio local puede sincronizarse mediante
`.\.venv\Scripts\python.exe scripts/inicializar_pool_sqlite.py`.
Registra en SQLite los endpoints `192.168.1.199:80018003` y sus asignaciones
persistentes `web:cuenta_0103`, y escribe `config/web_accounts.json`.
No crea reservas activas ni modifica mapeos diferentes existentes. El mapeo fija el endpoint de cada perfil web. Las placas Android pueden usarlo
cuando esta libre; una reserva activa o en cuarentena siempre impide compartirlo
entre procesos. Otros perfiles web no pueden apropiarse del mapeo. Cada ejecucion crea y libera su propia reserva normalmente.
El script usa las IPs de salida ya configuradas en `config/proxy_pool.json`;
no inventa salidas distintas ni ejecuta una verificacion de red completa.

El cargador de `.env` admite `OPENAI_API_KEY`, `GHOST_CURSOR_REPOSITORY` y
`GHOST_CURSOR_AUTOCLONE`, manteniendo precedencia de las variables del proceso.
`GHOST_CURSOR_REPOSITORY=https://github.com` se puede guardar, pero no identifica
un repositorio; la descarga seguira omitida hasta completar propietario y nombre.

Este modo usa Playwright con un perfil movil estandar y no depende de ADB. El
modo Android y sus comandos siguen disponibles. No garantiza indetectabilidad.

Preparacion en PowerShell desde la raiz del proyecto:

```powershell
Copy-Item config/web_accounts.example.json config/web_accounts.json
Copy-Item config/web_selectors.example.json config/web_selectors.json
.\.venv\Scripts\python.exe main.py --web-accounts config/web_accounts.json --web-login-only
```

Cada ventana corresponde a una cuenta. Inicia sesion manualmente y cierra esa
ventana al terminar. Los perfiles se conservan en `sessions/{account_id}`;
las sesiones pueden caducar y requerir autenticacion de nuevo. No se comparten
cookies entre cuentas. Los nombres de ejemplo deben sustituirse por tus
identificadores estables. Tambien se admiten objetos
`{"id":"cuenta_01","proxy":"192.168.1.199:8001"}` para fijar un endpoint.
La lista simple asigna los primeros proxies habilitados en orden.

El pool se toma de `config/proxy_pool.json`. Cada cuenta requiere un endpoint
exclusivo y su IP de salida esperada. Las reservas se coordinan en SQLite con
el modo Android. En laboratorio pueden compartir salida publica; en produccion
se requieren salidas distintas. Se comprueba la salida real por HTTPS antes
de abrir TikTok; un fallo detiene solamente esa cuenta.

Antes de consultar IA, reemplaza **todos los selectores requeridos** del archivo
`config/web_selectors.json`: dialogo de login, indicador de cuenta autenticada y
contenedor unico del video activo. Para ejecutar interacciones hacen falta
tambien los selectores de envio y cierre de comentarios. Like, apertura y campo de comentarios tienen selectores moviles predeterminados; pueden sobrescribirse en la configuracion. Los ejemplos son marcadores, no
selectores validados contra TikTok. El control de like debe exponer
`aria-pressed=true/false`, para no deshacer una interaccion existente.

```powershell
# Un ciclo de auditoria por cuenta; consulta IA y avanza el feed.
.\.venv\Scripts\python.exe main.py --web-accounts config/web_accounts.json --cycles 1
# Aplicar las decisiones de interaccion tras validar los selectores.
.\.venv\Scripts\python.exe main.py --web-accounts config/web_accounts.json --cycles 1 --execute
```

Las capturas se escriben en `logs/{account_id}/{timestamp}_{accion_tipo}.png`
con las etiquetas `post_decision`, `post_like`, `post_comentario` y `post_swipe`.
La auditoria JSONL por ejecucion conserva decisiones y tipos de error, sin
volcar credenciales. `logs/` y `sessions/` estan excluidos de Git. Un fallo de
captura se registra; si falta la captura de decision, se suspenden las
interacciones de esa cuenta. No se reintentan acciones cuyo resultado sea incierto.

`Ctrl+C` y `--stop-file` solicitan cierre cooperativo. Si vence
`--shutdown-grace` o el watchdog detecta un proceso congelado, se termina ese
proceso y su reserva queda en cuarentena cuando no se puede confirmar el
cierre del navegador. No liberes esa reserva sin comprobar primero que el
navegador anterior esta cerrado. Los resultados de cierre estan en
`runs/web-*/`. Los registros web no se mezclan con el inventario fisico del
dashboard Android.

Se reutiliza el cliente OpenAI y su esquema de decisiones actual. El ciclo es
sincrono dentro de cada proceso aislado; no se mezclan objetos Playwright
asincronos con sincronos. El viewport web es 390844.

El adaptador opcional se importa desde
`ghost_cursor.ghost_cursor.create_cursor`, en la raiz del proyecto. Debe ofrecer
`create_cursor(page).move_to(x, y)` sincrono. Si falta el adaptador, se inicia una preparacion en un hilo de segundo plano al importar el modulo
cuando `GHOST_CURSOR_REPOSITORY` contiene una URL completa de GitHub. El intento
usa un directorio temporal, publicacion por renombrado, bloqueo entre procesos y
timeout de 15 segundos. No sustituye carpetas existentes ni instala paquetes
con pip. `GHOST_CURSOR_AUTOCLONE=0` desactiva la descarga (la suite lo establece).
Si el arranque se interrumpe abruptamente, comprueba que no haya otra instalacion
activa antes de eliminar un posible `.ghost-cursor-install.lock` residual. `https://github.com` no es una URL de repositorio clonable:
hace falta `https://github.com/PROPIETARIO/REPOSITORIO`. El adaptador real aun no
se ha validado porque no esta presente. La preparacion en segundo plano carga el adaptador si la descarga termina correctamente.
Una instalacion manual posterior requiere reiniciar el proceso. La preparacion no modifica `sessions/`.

Si falta el modulo o falla su posicionamiento, se utiliza el arrastre estandar
con `page.mouse`, soltando el boton en `finally`. Son eventos de raton, no una
emulacion tactil de hardware. El arrastre distribuye 1830 movimientos durante 420680 ms; esto no implica
aceleracion fisica. La funcion toma una unica captura `post_swipe` al finalizar
el intento de arrastre, incluso si el envio o la liberacion del boton fallan. Los comentarios se escriben caracter por caracter con 60190 ms de
retardo. Los fallos de controles se auditan sin repetir el envio. Si no se puede
cerrar el panel de comentarios se detiene esa cuenta para no arrastrar sobre un
formulario pendiente. Tras un fallo de arrastre, el siguiente ciclo omite
interacciones y vuelve a intentar avanzar. Los selectores predeterminados son
candidatos de compatibilidad, no una validacion en vivo contra TikTok.



## Auditoria de red y ejecucion

El Panel de Control muestra las ultimas comprobaciones en Resultado de asignacion
 y verificacion de proxies. Auditoria de IA permite descargar los resultados de
red y las trazas de acciones en JSON. Cada evento incluye ejecucion, identificador,
endpoint, etapa, resultado, IP esperada/observada, latencia y tipo de error.

La reserva de un endpoint y la comprobacion HTTPS son etapas distintas. En Android
se verifica ademas la configuracion global leida de la placa y la salida bajo el
firewall. Un timeout o error de configuracion queda registrado aunque no haya IP.
La supervision periodica vuelve a comprobar la salida durante la ejecucion.

Para una prueba adicional desde Windows, sin modificar las placas:

```powershell
.\.venv\Scripts\python.exe scripts/auditar_proxies_windows.py
```

El resultado se guarda en SQLite y en `runs/diagnostico-windows-*/proxy-audit.json`.
Este diagnostico no confirma la asignacion Android ni el trafico del reproductor.
En laboratorio los tres endpoints comparten IP publica. Las trazas de acciones
registran intentos, comandos enviados y omisiones; la aceptacion por TikTok
permanece sin verificar. Un intento sin confirmacion de comando es incierto.
# QA fisico centralizado con Panda

El flujo adicional `main_panda.py` usa la API WebSocket local documentada de
Panda, con seleccion explicita por numero visual e identidad vinculada al inicio.
Consultar [guia de QA Panda](docs/PANDA_QA.md) para el preflight, la admision
manual, los ciclos finitos y la autorizacion opt-in de envio de capturas a OpenAI.
Las auditorias visuales privadas se separan de las tablas QA de metricas puras.
