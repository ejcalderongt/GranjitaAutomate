# Device map persistence

D-PERSIST.1..10: public salted references and recoverable private mappings.
Public files: runs/device_map_<timestamp>.json; hash_length_hex is 16.
Private files: secrets/device_map_<timestamp>.bin; plaintext exists only in memory.
Windows DPAPI protects private blobs for the current user, not the machine.
secrets/ and generated maps are excluded from Git; never publish their contents.
PANDA_DEVICE_SALT must be loaded from the root .env before saving or loading.
PANDA_DEVICE_MAP_KEEP defaults to 5 and controls complete pair retention.
Loaded pairs and pairs owned by other active or unqueryable PIDs are preserved.
Windows readers hold private files without delete sharing until process exit.
Corrupt or incomplete pairs are preserved; retention can therefore exceed KEEP.
Only superseded, valid, inactive pairs are eligible for removal.
load_latest_map returns None and logs device_map_corrupt on invalid latest pairs.
Loading never authorizes discovery or any external operation by itself.
The returned serials remain in memory; logs contain only fixed status messages.
Selection integration is described in the Hito 3 corregido section below.

## Hito 3 corregido

Combined execution requires an explicitly supplied inventory and validated limits.
Standalone preflight and execution without farm preflight keep their prior routing.
Proxy validation runs once before farm checks; abort prevents native execution.
Only CSV identities are admitted, bound to DPAPI references and live physical identity.
Missing, duplicate or inconsistent bindings fail; discovery never fills missing plates.
Failed or unaligned plates are excluded; insufficient admitted count aborts execution.
Completed native runs add one farm_stage_metrics row with three NULL counters.
Cancellation preserves 130 and produces no completed native metric sample.
C5 ignores incomplete samples; zero complete samples yield WARN, never invented zeros.
Existing thresholds and FAIL for accredited incidents remain unchanged.
Declared writes are final row changes by key and current run_id, not SQL counts.
Normal three-plate, one-cycle runs insert three auditorias_panda rows and three AI events.
Previous rows, unrelated tables, schema and unrelated sequences remain immutable.
telemetria_panda.db may change through farm rows and declared auditorias_panda inserts.
telemetry_qa.db may change only through declared eventos_ia_qa inserts and its sequence.
Outside a declared run telemetry_qa.db has an immutable whole-file hash.
All other protected database files always retain their whole-file hashes.
Evidence contains row-key hashes, declared/observed writes and before/after file hashes.
Pending: prepare required native schemas explicitly before the first physical baseline.
Pending: real CSV preflight and controlled physical execution require a later prompt.
Plan de etapas vigente: docs/PLAN_ETAPAS.md.

### E-2 CSV autorizado

`tests/fixtures/csv/lab_stage3.csv` es la fuente de verdad de las tres placas para E-2.

| Placa | Panda | Transporte | Alias | device_ref |
|---|---|---|---|---|
| p01 | 02 | 192.168.1.150:5555 | Analu Hernandez | b236403581fd1f7d |
| p02 | 04 | 192.168.1.167:5555 | Experimento GT | 82b5c03f65bc12d8 |
| p03 | 05 | 192.168.1.152:5555 | SM-G973F | bb360a6246550522 |

Seleccion confirmada de las primeras tres fichas elegibles en orden Panda.
Se cruzo Panda vivo con el lote acreditado del 2 de noviembre y las rutas activas en 5037.
Se excluyeron la ficha 01, las dos identidades del incidente y las rutas ausentes,
ambiguas o distintas de las acreditadas. Hallazgo de seleccion: `5038_listening=true`.
Evidencia local: `runs/e2_csv_selection_20261106T174934205351Z.json`.

`load_latest_map` ignora nombres sin timestamp valido. Los dos informes de pruebas
se conservaron byte a byte con prefijo `report_device_map_` fuera de Git.
El mapa inicial DPAPI se comprobo contra las referencias del CSV.

### Correccion de la ruta de preflight aislado

El preflight aislado con inventario explicito y `--expected-count 3` valida el CSV
y el mapa DPAPI antes del preflight de proxy. Usa solo las rutas del CSV en los
servidores del mapa y verifica cada identidad fisica. Una ruta ausente o una
identidad distinta provoca un error de configuracion sin sustitucion de placas.
Sin inventario explicito, conserva la seleccion previa.

Pruebas: `tests/test_panda_massive_preflight_farm_cli.py` y
`test_cli_no_automatic_plate_substitution` en `tests/test_panda_massive_cli_integration.py`.

### Sustitucion de p01 en E-2

Fecha: 2026-11-07, America/Guatemala. Commit base: b8d52ec.
Esta seleccion actualiza la tabla historica de E-2 CSV autorizado.

La p01 original permanecio en es-GT tras cerrar Ajustes y esperar 30 segundos.
Reporto sales_code CHL, countryiso_code US y product locale en-US. Se detectaron
un administrador activo y paquetes de gestion. La clasificacion mdm_bloqueado
aplica las reglas del prompt; la causalidad entre esos indicadores y el locale
no quedo acreditada. Evidencia: runs/e2_p01_diagnostico_20261107T141315671713Z.json.

| Placa | Panda | Transporte | Alias | device_ref | Locale |
|---|---|---|---|---|---|
| p01 | 13 | 192.168.1.174:5555 | EL POSEIDON | 6f70ba1186f2dcd4 | es-ES |

La ficha 07 no cumplio los filtros. La 13 fue la siguiente candidata elegible,
con identidad fisica verificada en 5037. El operador confirmo el idioma y la
lectura posterior devolvio es-ES. Las filas p02 y p03 se conservaron byte a byte.

Nuevo mapa publico: runs/device_map_20261107T142303177829Z.json.
El par privado DPAPI permanece fuera de Git en secrets/. El CSV canonico y el
mapa coinciden para p01, p02 y p03, y la seleccion canonica del CLI fue validada.
La zona horaria de la nueva p01 y la alineacion de p02 y p03 quedan pendientes.

### Diagnostico de p02 y p03

Fecha: 2026-11-07, America/Guatemala. Commit base: a09f55b.
Diagnostico de solo lectura; sin pantallas, cambios de ajustes, retirada de
paquetes ni preflight. Identidades verificadas en el servidor local 5037.
El transporte de p02 cambia de 192.168.1.167:5555 a 192.168.1.171:5555:
la ruta nueva corresponde fisicamente a Panda 04. Panda 05 fue reconectada
previamente en 192.168.1.152:5555 y su identidad se verifico de nuevo.

| Placa | Panda | CSC | Pais CSC | Product locale | Locale actual | Zona actual | Clasificacion AU-2 |
|---|---|---|---|---|---|---|---|
| p02 | 04 | CHC | CN | zh-CN | es-GT | America/Guatemala | mdm_bloqueado |
| p03 | 05 | CHL | US | en-US | es-GT | America/Guatemala | mdm_bloqueado |

Ambas contienen com.sec.enterprise.mdm.services.simpin. Panda 05 contiene
ademas com.samsung.android.mdm y com.sec.enterprise.knox.cloudmdm.smdms.
La clasificacion aplica literalmente AU-2 por presencia de paquetes de gestion.
No acredita enrolamiento MDM activo, una restriccion efectiva sobre idiomas ni
causalidad del fallo de UI. Los indicadores CSC no corresponden a Guatemala.
ro.product.locale describe el valor de fabrica, no prueba que sea inmutable.

Se consulto el inventario vivo mediante obtener_inventario con adaptador SQLite
de solo lectura y servidor explicito 5037: 34 fichas, 21 vinculadas con identidad
fisica verificada. Tras excluir 01, 02, 04, 05, 13, 16 y 31, se diagnosticaron
17 candidatas: 10, 12, 14, 15, 22, 23, 24, 26, 27, 28, 33, 37, 45, 46, 48, 55
y 56. Todas presentan paquetes de gestion
y es-GT; ninguna es sustituta elegible bajo la regla AU-2. El informe local es
la fuente exacta de fichas y resultados; no se extrapola a rutas desconectadas.

Decision: bloqueado_por: pool sin candidatas elegibles.
No se sustituyen filas ni se regenera DPAPI; la seleccion canonica conserva
Panda 13, 04 y 05. Panda 13 ya reportaba es-ES y Europe/Madrid.
Evidencia: runs/e2_p02_p03_diagnostico_20261107T155932255151Z.json.

Se recomienda evaluar adoptar GT, pendiente de aprobacion humana explicita
con adoptar GT. No se modifica .env ni la politica. Esta alternativa requiere
PANDA_POLICY_COUNTRY=GT, PANDA_PROXY_COUNTRY=GT y pool de proxy verificado en GT.
C2 solo podria mejorar si sus comprobaciones reales de SIM y GeoIP coinciden;
no garantiza PASS ni elimina otros bloqueos. No se ha ejecutado preflight real.

Validacion: 485 pruebas pytest y 25 subtests, 483 pruebas unittest, todas PASS.
Credenciales reales aisladas; guardia de bases sin accesos y hashes G/Q intactos.

### Reclasificacion de mdm_bloqueado y sustitucion de p02 y p03

Fecha: 2026-11-07, America/Guatemala. Commit base: be4cac6.
AU-R1 reemplaza el descarte por mera presencia de paquetes de gestion.
Las 17 candidatas reportaron no owners mediante dpm list-owners y no mostraron
restricciones explicitas de locale en dumpsys device_policy. Se reclasificaron
mdm_presente_sin_bloqueo; no se acredita ausencia universal de gestion MDM.

El operador selecciono el idioma; el agente solo abrio Ajustes y verifico
identidad fisica, persist.sys.locale y persist.sys.timezone en 5037.
Panda 10, 12 y 14 siguieron en es-GT y America/Guatemala y quedaron ui_no_aplica
segun los prompts de continuacion, sin inferir bloqueo MDM. Panda 15 y 22
reportaron es-ES y Europe/Madrid en la verificacion final de ambas.
Se detuvo el escaneo al obtener dos candidatas aptas.

| Placa | Panda | Transporte | Alias ASCII | device_ref | Locale | Zona |
|---|---|---|---|---|---|---|
| p01 | 13 | 192.168.1.174:5555 | EL POSEIDON | 6f70ba1186f2dcd4 | es-ES | Europe/Madrid |
| p02 | 15 | 192.168.1.143:5555 | ALEXANDER FRANCO | 7b3ae937f7cd79f3 | es-ES | Europe/Madrid |
| p03 | 22 | 192.168.1.153:5555 | El Poseidon | f1044d84929f0277 | es-ES | Europe/Madrid |

La fila p01 se conserva. Panda 04 y 05 salen de la seleccion E-2; no se alteran
sus ajustes en este paso. El CSV canonico contiene ahora Panda 13, 15 y 22.
Se regenero el mapa por el cambio de referencias de p02/p03:
runs/device_map_20261107T163041377222Z.json y su par privado DPAPI en secrets/.
load_latest_map y la seleccion canonica del CLI con expected_count=3: PASS.
Evidencia: runs/e2_candidatas_reclasificadas_20261107T160548305752Z.json.

Decision: E-2 listo para verificar alineacion y continuar con el preflight
en un paso posterior autorizado. No se retiraron paquetes ni se ejecuto
preflight real. No se adopta GT ni se modifica .env, politica o proxies.

Verificacion final: las tres identidades, es-ES y Europe/Madrid confirmadas.
Pruebas aisladas: 485 pytest y 25 subtests, 483 unittest, todas PASS.
Hashes G/Q antes/despues identicos; guardia de bases sin accesos en las suites.

### Diagnostico del preflight real E-2: codigo 1

Fecha: 2026-11-07, America/Guatemala. Commit base: f31ef54.
El intento unico farm-0f809e35e5804fadaa28e12e70450b21 verifico el proxy y
termino con Configuracion invalida, codigo 1. No se repite en este diagnostico.
Los nueve retiros autorizados terminaron con exito en el intento anterior;
no se retiran paquetes adicionales. Sin ADB, pantallas o cambios de entorno.

Causa: bug del adaptador C3 dentro de run_farm_preflight. build_real_context
con CSV explicito usa numeros Panda 13, 15 y 22. El adaptador reutilizaba
evaluate_c3/records, que exige identificadores pNN. records lanza ValueError
Fixture sintetico invalido, capturado por ejecutar_preflight_farm_solo como
EXIT_CONFIG_ERROR. main emite EXIT_MESSAGES[1] desde config/farm_policy.py.
El mensaje generico menciona PANDA_POLICY_* aunque la politica carga bien.
canonical_selection, CSV/DPAPI y load_farm_policy actuales validan sin error.

La ruta real fue main_async -> ejecutar_preflight_farm_solo; no incluyo
execute_read_only ni la corrida combinada. El registro SQLite existente
prueba que C1 y C2 se evaluaron antes del error. El JSON final quedo sin
verdicts porque run_farm_preflight no retorno su lista al caller. Esto corrige
la interpretacion anterior de que C1-C5 no habian sido evaluados.

| Constraint historica | Estado | Detalle |
|---|---|---|
| C1 | FAIL | negative_automation_apps=3; Play Integrity sin acreditar |
| C2 | WARN | missing_sim_country=3; mismatches=0; proxy_verified=true |
| C3 | ERROR | Identificadores incompatibles con records |
| C4/C5 | NO EVALUADAS | No se alcanzaron |

Fix minimo: el adaptador local C3 renombra sus claves planificadas a p01..p03
y conserva cada hold_seconds. No cambia identificadores fisicos de otros
adaptadores, politica, limites, codigos de salida ni contrato de records.
Dos regresiones hermeticas cubren numeros Panda reales, holds validos y
preservacion de valores ausentes o fuera de rango, con SQLite en memoria y
conectores simulados. Las pruebas dirigidas autorizadas: 22 PASS.

Evidencia: runs/e2_preflight_diagnostico_20261107T164318470371Z.json.
Decision: listo_para_reintentar_preflight desde el punto de vista del bug C3.
El reintento requiere autorizacion separada; E-2 no esta cerrado. El C1 FAIL
historico por automatizacion sigue pendiente: conservar io.appium.* fue
autorizado y este fix no altera su deteccion ni rebaja FAIL a WARN.

Validacion del fix: 487 pytest y 25 subtests, 485 unittest, todas PASS.
Credenciales aisladas, guardia sin accesos a bases protegidas y hashes G/Q
sin cambio. No se ejecuto preflight completo ni ADB durante el diagnostico.

### E-2 ejecucion real

Fecha: 2026-11-07, America/Guatemala. Commit base: ed66e28.
Se verificaron CSV/DPAPI, identidad fisica y rutas en 5037 para Panda 13, 15 y
22. Las tres reportaron es-ES y Europe/Madrid. Los tres paquetes previamente
autorizados para retirada estan ausentes en las tres placas. No se retiraron
paquetes adicionales. El FAIL historico de C1 tambien fue posterior a esos
retiros, segun runs/e2_execution_20261107T163855788930Z.json.

Se ejecuto una sola vez el comando AU-1, incluido execute-read-only, un ciclo,
concurrency=1 y hold-seconds=12. El preflight aborto antes del flujo nativo:
codigo 2, decision abort, synthetic=false. No se abrieron pantallas.

| Constraint | Estado | Resultado |
|---|---|---|
| C1 | FAIL | negative_automation_apps=3; negative_uid_privileged=0; negative_emulator_hint=0; Play Integrity no acreditado |
| C2 | WARN | missing_sim_country=3; mismatches=0; proxy_verified=true |
| C3 | PASS | checked=3; failed=0; missing=0 |
| C4 | FAIL | distinct=1; total=3; errors=0; timeouts=0; minimo requerido=3 |
| C5 | WARN | samples=0; no acredita ausencia de incidentes |

Evidencia: runs/farm_preflight_panda-masivo-27ebb82673404582963be92c12646581.json.
Ejecucion: runs/e2_execution_20261107T170051895331Z.json.
Hashes G/Q antes y despues identicos. No se modificaron configuracion o politica.

#### Correccion del bug C3 en la corrida

La correccion ed66e28 permite completar C3 con los numeros Panda del CSV.
La comprobacion de holds planificados es PASS; no acredita interaccion nativa.
Los cinco veredictos estan presentes, sin el codigo 1 anterior.

#### Diagnostico residual C1

La lectura posterior de pm list packages encontro en cada placa los paquetes
io.appium.uiautomator2.server y io.appium.uiautomator2.server.test. Son los
detectados por build_real_context.integrity en config/farm_preflight.py, no
por device_map. Su conservacion estaba autorizada. No se retiraron ni se
modifico el criterio C1. Evidencia: runs/e2_c1_residual_20261107T170051895331Z.json.

Decision: bloqueado_por: C1_FAIL_persistente y C4_FAIL.
E-2 no se cierra; no se hace commit de cierre ni push. Pendiente decision
humana sobre Appium y diagnostico autorizado de la diversidad del proxy.
Sin reintento automatico, sin nuevas suites por no haber cambios de codigo.

### C1 excluye Appium y C4 ajusta minimo de etapa 3

Fecha: 2026-11-07, America/Guatemala. Commit base: ed66e28.
DH-1: io.appium.* es infraestructura autorizada del laboratorio. El detector
real no la cuenta como negativa ni excluye por ella las placas del CSV.
appium_present y appium_ignored cuentan dispositivos con Appium, no paquetes;
no afectan al estado. Root, emulador, Play Integrity y otros negativos conservan
su tratamiento. Se detectan com.genfarmer.*, com.topjohnwu.magisk,
com.genymobile.scrcpy y scrcpy. No se encontro el codigo device-agent en este
checkout para cotejar otra lista; estos patrones siguen los ejemplos del prompt.
Se conserva la compatibilidad con probes antiguos que solo entregan booleanos.

DH-2: el default C4 pasa a 1 salida distinta en etapa 3, 3 en etapa 10 y 5 en
etapa 34. Una configuracion explicita sigue prevaleciendo. stage_limits publica
el minimo efectivo. No se cambia .env ni el proveedor ni config/proxies.py.
DH-3: esta aceptacion de etapa 3 acredita disponibilidad con al menos una salida,
no diversidad ni capacidad para etapas mayores. Los otros umbrales no se relajan.

El humano autorizo ampliar las funciones a build_real_context.integrity, el
contrato de contadores C1 y load_farm_policy para aplicar el cambio de extremo
a extremo, sin excepciones locales que falseen los verdicts.

Diagnostico del pool sin conexiones nuevas, segun Fase 4 del prompt: evidencia
historica real distinct=1, total=3, errors=0, timeouts=0. No se realizaron cinco
muestras nuevas ni se presenta un replay como medicion actual. Esa observacion
no demuestra el limite contractual del proveedor ni su diversidad futura.
Evidencia: runs/e2_c4_pool_diagnostico_20261107T170451862455Z.json.
Criterio C1: runs/e2_c1_appium_policy_20261107T170451862455Z.json.

No se ejecuto preflight real ni ADB ni se retiraron paquetes. Pendiente reintento
autorizado para comprobar C1 y C4 en vivo; no se declara E-2 cerrado.

El humano autorizo fijar minimo=3 en el helper de los tests C4 existentes,
preservando sus expectativas de diversidad; los nuevos tests cubren el nuevo
default por etapa y la prioridad de una configuracion explicita.
Validacion final: 491 pytest y 28 subtests, 489 unittest, todas PASS, con
credenciales aisladas. Hashes G/Q identicos antes/despues; guardia sin accesos.

### Diagnostico de Proxy no verificable

Fecha: 2026-11-07, America/Guatemala. Commit base: 509a5ab.
El intento panda-masivo-28a008d265e54b29bd6b5ae172a66bbd termino con codigo 4
antes de evaluar C1-C5. No se repitio el preflight completo ni se uso ADB.
PANDA_PROXY_COUNTRY esta presente y coincide con ES; el cargador y la
configuracion del manager validan sin exponer parametros privados.

ProxyManager.verificar_preflight obtiene la salida directa, crea el puente,
consulta ipify mediante Patchright y luego consulta GeoIP mediante el puente.
Captura errores y emite RuntimeError Proxy no verificable cuando la validacion
o la limpieza fallan. ejecutar_preflight_proxy_solo convierte la excepcion en 4.
El log historico no conserva la subcausa original: no puede afirmarse que sea
identica a la observacion aislada actual.

Diagnostico aislado autorizado, sin navegador: consulta directa correcta en
416 ms; puente iniciado y escuchando; consulta ipify por el puente con
ReadTimeout a 10003 ms. Clasificacion observada: timeout_ipify. Sin IP de salida
no se pudo comparar fuga ni consultar GeoIP; quedan no evaluadas, no FAIL.
La escucha del puente no acredita autenticacion o transporte hacia el upstream.
Tampoco se confirmo el cierre limpio del puente antes de terminar el script;
su proceso ya termino. Esto puede contribuir al fallo generico de limpieza,
pero no prueba que fuera la causa del preflight historico.

Evidencia sin IPs ni credenciales:
runs/e2_proxy_diagnostico_20261108T003821316663Z.json.
Pruebas autorizadas: test_proxy_manager_salidas y
test_panda_massive_cli_integration, 14 PASS, con credenciales aisladas.
Hashes G/Q antes/despues identicos. Sin cambios de codigo, .env o politicas.

Accion propuesta: verificar disponibilidad y autenticacion del endpoint
contratado y su conectividad desde este host con el proveedor. No hay evidencia
para proponer un valor nuevo de configuracion ni para ampliar timeouts como fix.
Pendiente autorizacion para un nuevo diagnostico de transporte o reintento
tras resolver el timeout. E-2 sigue bloqueado; no se declara proxy operativo.

#### Instrumentacion y reintento controlado del diagnostico

Fecha local: 2026-11-07. Base: d9ba41a. Sin preflight real ni ADB.
verificar_preflight ahora distingue causas mediante prefijos proxy_preflight_*,
con booleanos y duraciones; mantiene Proxy no verificable como error externo.
La limpieza intenta bridge.close en finally aunque falle cerrar_contexto_async.
Los dos tests nuevos verifican timeout ipify y cierre invocado tras fallo del
navegador, sin red. Suite dirigida de proxy: 8 PASS.

El unico reintento autorizado por el puente agoto 15009 ms (ReadTimeout).
La salida directa respondio en 368 ms. El puente escuchaba localmente pero no
confirmo cierre limpio; el proceso aislado termino. La conexion TCP al endpoint
agoto 5000 ms, sin completar handshake SOCKS5 ni autenticacion. No demuestra
culpa exclusiva del proveedor ni descarta ruta/firewall local. No se pudo
evaluar fuga ni GeoIP. Clasificacion final: unknown; fallo observado timeout_ipify.

Evidencia: runs/e2_proxy_diagnostico_20261108T004137775329Z.json y
runs/e2_socks_transport_20261107.json, sin direcciones ni credenciales.
No se falsea bridge_closed=true. Pendiente autorizacion para revisar el ciclo
de cierre en socks_bridge.py, fuera del alcance original. Sin mas reintentos.

#### Correccion autorizada del cierre del puente

El humano amplio el alcance a socks_bridge.py y tests locales, sin nuevas
consultas externas. Se identifico una espera circular: Server.wait_closed
podria esperar clientes activos antes de cancelar sus handlers. El puente ahora
registra sus transportes aceptados, deja de aceptar, aborta esos transportes,
cancela handlers y despues espera el cierre del servidor y del loop. No toca
conexiones de otros procesos ni servidores ADB. close sigue siendo idempotente.

Las pruebas locales cubren un cliente detenido antes del handshake, cierre
antes de start, el tunel local existente y la limpieza tras fallar el navegador.
El log distingue el resultado de cierre del puente del resultado del navegador.
El mensaje externo conserva Proxy no verificable. No se registran excepciones
crudas, direcciones, URLs o credenciales en los eventos nuevos.

Evidencia nueva: runs/e2_proxy_diagnostico_20261108T004655939161Z.json,
bridge_closed=true, hilo terminado, loop cerrado, listener cerrado, sin red
externa. No se altera la evidencia previa bridge_closed=false: correspondia
al codigo anterior. La causa del timeout externo sigue unknown y E-2 bloqueado;
corregir la limpieza no acredita disponibilidad del proveedor.

Validacion: 495 pytest y 28 subtests, 493 unittest, todas PASS. Tras separar
el booleano del puente en el log, 11 pruebas dirigidas adicionales PASS.
Hashes G/Q antes/despues identicos, credenciales aisladas y guardia sin accesos.

### Diagnostico de red del pool

Fecha local: 2026-11-07, America/Guatemala. Base: 3ad608b.
Configuracion cargada y validada, pais esperado presente. Sin cambios de .env,
codigo funcional, politicas, ADB, pantallas, consultas HTTP ni preflight real.
Se consulto DNS y TCP del endpoint configurado en tres muestras, separadas
por tres segundos, con limite de quince segundos para cada prueba.

| Muestra | DNS | DNS ms | Direcciones resueltas (conteo) | TCP | TCP ms |
|---|---|---|---|---|---|
| 1 | PASS | 94 | 1 | TimeoutError | 15000 |
| 2 | PASS | 0 | 1 | TimeoutError | 15000 |
| 3 | PASS | 0 | 1 | TimeoutError | 15000 |

samples_ok=0, samples_fail=3. Handshake SOCKS5, autenticacion y CONNECT no
evaluados por ausencia de conexion TCP; no se afirma rechazo de credenciales.
Clasificacion segun AU-2: red_local, por fallo TCP consistente desde este host.
Limite causal: estas pruebas no distinguen firewall del equipo, ruta, filtrado
remoto o indisponibilidad del endpoint. No prueban culpa exclusiva de red local
ni del proveedor. No hay evidencia para cambiar credenciales o politica.

Evidencia: runs/e2_proxy_red_20261108T010014221626Z.json. Script local no
versionado: runs/_diagnostics/pool_network.py. Sin direcciones o secretos en
la evidencia publica. Hashes G/Q antes/despues identicos.
Decision: bloqueado_por: red_local segun la regla acordada. Pendiente humano:
revisar reglas de salida del firewall, VPN y ruta del equipo hacia el endpoint;
si no aparece bloqueo local, contrastar accesibilidad y filtros con el proveedor.
No se desactiva firewall/VPN ni se modifica configuracion por cuenta del agente.

Validacion: 495 pytest y 28 subtests, 493 unittest, todas PASS. Credenciales
aisladas y guardia sin accesos; hashes protegidos intactos antes y despues.

### Fuente canonica del proxy

Fecha local: 2026-11-07, America/Guatemala. Base: 50b55c5.
La fuente efectiva actual es el .env raiz. Contiene PANDA_PROXY_HOST,
PANDA_PROXY_PORT, PANDA_PROXY_USER, PANDA_PROXY_PASS, PANDA_PROXY_SCHEME y
PANDA_PROXY_COUNTRY. Sus valores son sensibles y no se copian a documentacion.
La premisa de que solo existen tres claves PANDA_* no coincide con la lectura
actual del archivo; no se infiere quien o cuando lo actualizo.

ProxyManager.desde_panda, en config/proxies.py, lee dotenv_values con
interpolate=False y luego superpone os.environ. Se verifico en memoria que
host, puerto, usuario, password y esquema del manager corresponden a la fuente.
No hay PANDA_ENV_FILE alternativo ni overrides de las seis claves en el proceso
de comprobacion. load_project_environment no exporta las claves de conexion,
pero eso no impide su lectura directa por desde_panda. No requiere modificar
el loader ni migrar o reescribir .env: migration_needed=false.

config/local_proxy.local.json contiene datos del servicio local pero no los
cinco campos de autenticacion completos. config/proxy_pool.json contiene
entradas de pool pero tampoco los cinco campos. config/proxies.json no existe.
Se detuvo la busqueda al acreditar la fuente efectiva; no se consultaron
credenciales de SQLite, sesiones, registros antiguos o sistema Windows.

Con esa fuente verificada se repitieron tres muestras: DNS correcto en todas;
TCP TimeoutError en 15000, 15015 y 15000 ms. Handshake, autenticacion y CONNECT
no evaluados porque no se obtuvo conexion TCP. No se prueba fallo de password.
Clasificacion por la regla acordada: red_local (0 muestras exitosas, 3 fallidas),
sin atribuir culpa exclusiva al firewall del host ni descartar filtrado remoto.

Evidencia sin valores sensibles: runs/e2_proxy_fuente_20261108T011825153321Z.json.
Decision: bloqueado_por: red_local. La fuente ya es canonica; pendiente revisar
ruta y accesibilidad del endpoint con la red o el proveedor. Sin migracion,
preflight real, ADB, pantallas o cambios de configuracion. Hashes G/Q intactos.

Suites aisladas: 495 pytest y 28 subtests, 493 unittest, todas PASS. Guardia
sin accesos a bases protegidas y hashes G/Q antes/despues iguales.

### Soporte de esquemas http y https en ProxyManager

Base: 43d82f4. El cambio autorizado de .env a http ya estaba aplicado y no se
modifico de nuevo. Se preparo un cambio local del normalizador que acepta
http y https y conserva socks5/socks5h como socks5, sin tocar el puente.
proxy_para_chromium ya pasa HTTP/HTTPS directamente; no requiere traduccion
del upstream a SOCKS5. No se altera el contrato legacy del proveedor.

Cuatro tests nuevos cubren HTTP, HTTPS, compatibilidad SOCKS5/SOCKS5h y rechazo
de esquema desconocido. Suite dirigida de esquemas y proxy: 12 PASS.
La verificacion efectiva usa browser_proxy, ya que ProxyManager no ofrece get;
el esquema observado es http. No se imprimen valores sensibles.

La unica consulta curl autorizada a ipify devolvio HTTP 000 y exit_code 28,
timeout de veinte segundos. Credenciales pasadas por stdin, sin exponerlas en
argumentos ni registros. No se ejecuto el preflight de proxy, porque AU-4 exige
HTTP 200. Clasificacion: red_aun_fallando. Hashes G/Q antes/despues intactos.
Evidencia: runs/e2_proxy_http_20261108T043253711328Z.json.

Segun Fase 4, con HTTP 000 no se commitea codigo, salvo documentacion.
El normalizador y tests nuevos permanecen como cambios locales pendientes de
publicacion autorizada. No se declara proxy operativo ni E-2 cerrado. Pendiente
resolver conectividad del endpoint antes de otro intento; no se modifica .env.

Validacion local completa: 499 pytest y 28 subtests, 497 unittest, todas PASS,
credenciales aisladas y guardia sin accesos a bases protegidas.

### Escalado por etapas (preparacion local)

Fecha: 2026-11-08. Cola autonoma autorizada desde 443a06e. Sin ADB, preflight
real, llamadas a OpenAI, imagenes de dispositivos o cambios de .env.
El ticket del proveedor consta preparado; no se acredita envio desde el agente.

--stage {3,10,34} y --stage-limits <json> en main_panda_masivo planifican
transiciones offline. No se combinan con ready, execute-read-only, Vision o
preflight; esas combinaciones devuelven error de configuracion sin dispositivos.
El resultado se guarda en runs/stage_plan_<id>.json, con executes_next_stage=false.
La base indicada por --db se abre en mode=ro; no se crean esquemas o filas.

Ejemplo: `.venv\Scripts\python.exe main_panda_masivo.py --stage 3 --db <historial>`.
--stage-limits acepta exactamente las claves 3, 10 y 34, cada una con min_samples
entero entre 1 y 10000. Sin archivo se exige al menos una muestra completa.
El historial se limita a la ultima corrida fisica finalizada de esa etapa.
Una muestra incompleta, NULL, schema ausente o corrida sintetica no acredita
promocion. Cualquier captcha, softblock o logout observado aborta incluso si
otra columna es NULL. Se requiere corrida aceptada y C4 PASS historico.
Con muestras completas sin incidentes: 3 propone 10, 10 propone 34 y 34 completa.
La propuesta nunca ejecuta la siguiente etapa ni acredita sus limites de proxy.
Los defaults de salidas requeridas siguen siendo 1/3/5; no se cambia politica.

tests/test_stage_scaling.py cubre etapas 3/10/34, incidentes, NULL, muestras,
historia sintetica, C4, JSON de limites y aislamiento del flujo nativo.
Esto prepara E-6; las corridas fisicas E-2/E-3 y la aceptacion real de escalado
siguen pendientes del proxy y de sus prompts autorizados.

La fase A prepara contratos tipados y servicio Vision con clientes simulados;
ver docs/VISION_PREPARATION.md. La fase B entrega el panel local y evidencia
filtrada; ver docs/LAB_UI.md. No se declara completo el laboratorio fisico.
La correccion previa autorizada del puente elimina la carrera de aceptacion
durante cierre; fue validada con 20 conexiones locales y suites aisladas.

Validacion final de la cola: 542 pytest y 28 subtests, 540 unittest, todas PASS.
La UI anade 13 pruebas de autorizacion/evidencia/cancelacion; Vision 15 pruebas;
escalado 14 pruebas. Las capturas son renders reales de fixtures locales, no de
dispositivos. Guardia sin accesos a bases protegidas y hashes G/Q intactos.
Aviso no bloqueante: la version instalada de Starlette recomienda migrar su
TestClient a httpx2; se conserva httpx existente porque los tests pasan.

### Panel, playbook E-3 y matriz de red (2026-11-09)

El panel local arranco en http://127.0.0.1:8000 y GET /api/status devolvio 200.
El playbook de E-3 especifica los comandos, requisitos, observacion humana,
evidencia y criterios de parada para una corrida autorizada.

La matriz probo seis puertos y dos protocolos. DNS dio una direccion IPv4 y
cero IPv6. Dos combinaciones alcanzaron el destino HTTPS de prueba con
autenticacion. En los cinco puertos alternativos vencio el plazo TCP. Los
resultados de IPv6 quedan como no evaluados por falta de registro.

La combinacion HTTP exitosa coincidia con los valores configurados. El
preflight aislado se ejecuto una vez y devolvio codigo 4. Se conservo el
codigo, pero no el detalle interno de la excepcion. La conectividad al
destino de prueba quedo verificada. La verificacion completa sigue pendiente.

Evidencia: runs/e2_proxy_deep_diag_20261109T151352257817Z.json.
Ticket preparado: runs/e2_proxy_support_ticket_final_20261109T151352257817Z.txt.
El ticket distingue los timeouts anteriores del resultado actual y pide
confirmar disponibilidad, filtrado y puertos asignados. Queda listo para
envio por el operador. E-2 permanece pendiente del preflight de proxy.

### Traza y correccion del preflight de proxy (2026-11-09)

Base: 0c21493. La traza inicial devolvio 4 con stage=geoip y cause=auth_407.
El navegador ya habia alcanzado el destino de IP. El cliente HTTP de GeoIP
creaba su conexion al proxy sin la autenticacion disponible en las opciones
del navegador. El cliente ahora usa esa autenticacion cuando esta presente.
Un caso local con clientes simulados confirmo el traspaso de autenticacion.

El wrapper conserva el tipo y los mensajes controlados de las excepciones.
El resto de los mensajes se reserva. El verificador registra la etapa y
detecta 407 tanto en la respuesta HTTP como en la excepcion del tunel CONNECT.
Se conserva el contrato de error Proxy no verificable.

La unica verificacion posterior al cambio devolvio 4 con stage=ipify,
cause=timeout_ipify y error_type=TimeoutError, antes de llegar a GeoIP.
Por tanto, el traspaso de autenticacion tiene validacion local y falta
validarlo de extremo a extremo. Se agotaron los dos intentos autorizados.
La matriz anterior verifico ipify, y no aporto evidencia sobre icanhazip.

Evidencia inicial: runs/e2_preflight_trace_20261109T151938927398Z.json.
Evidencia final: runs/e2_preflight_final_20261109T152012723686Z.json.
La captura conserva las lineas de diagnostico de formato conocido y omite
las demas. La causa registrada en esa corrida fue timeout_ipify.

### Migracion de la verificacion de IP a icanhazip (2026-11-09)

El preflight aislado consulta el mismo endpoint IPv4 de icanhazip tanto
desde el host como desde el navegador con proxy. El plazo de cada consulta
es de 25 segundos. El verificador acepta texto plano y elimina el salto de
linea antes de validar la direccion. Para la consulta directa tambien
admite el formato JSON de los clientes existentes. La comparacion de fuga y
la validacion GeoIP siguen vigentes.

Una corrida real devolvio codigo 0 y Proxy verificado. La evidencia esta
en runs/e2_preflight_final_20261109T152516546562Z.json. La prueba acredita
el endpoint nuevo para esta corrida y deja listo el siguiente paso E-2.

### E-2. Preflight de granja detenido (2026-11-09 UTC)

Base e368e19. El unico intento autorizado uso el CSV canonico de tres
placas. El proxy devolvio Proxy verificado. El precheck real de granja
termino con codigo 1, fuera de los codigos permitidos, y decision
precheck_failed. El mensaje de la CLI indica que las rutas del inventario
no coinciden con las identidades del mapa DPAPI. El mensaje agrupa varios
fallos de seleccion y lectura. La traza no identifica la placa afectada.

| Constraint | Estado | Contadores |
|---|---|---|
| C1 | No evaluado | Sin datos |
| C2 | No evaluado | Sin datos |
| C3 | No evaluado | Sin datos |
| C4 | No evaluado | Sin datos |
| C5 | No evaluado | Sin datos |

La evidencia registra synthetic=false y verdicts=[]. El cierre requiere
primero validar las rutas y las identidades de las tres placas, y despues
obtener veredictos en una nueva corrida autorizada.

Evidencia: runs/farm_preflight_farm-0dabbe640b8b4446acd667d745e0d7f5.json.
Traza: runs/e2_farm_trace_20261109T153154788643Z.json.

### Sincronizacion de rutas E-2 (2026-11-09 UTC)

Base e368e19. En el diagnostico de 5037, las rutas previas de p01 y p02
respondieron con identidades diferentes de las seleccionadas en DPAPI. La
ruta previa de p03 estaba ausente. Se encontraron las identidades esperadas
de p01 y p03 en rutas nuevas. Panda identifico p02 en otra ruta y, tras una
conexion autorizada, ADB confirmo su identidad fisica en 5037.

Se actualizaron solo los tres campos transporte del CSV canonico. Las
referencias y las identidades del mapa se conservaron. El cruce por serial
fisico permitio mantener la seleccion aunque los numeros visibles en Panda
para p01 y p02 habian cambiado.

El unico preflight posterior al cambio completo evaluo las tres placas.
El proxy paso y el informe registro synthetic=false, codigo 2, decision abort.

| Condicion | Estado | Contadores principales |
|---|---|---|
| C1 | FAIL | checked=3, negative_automation_apps=3, appium_ignored=3, integrity_probe_errors=3 |
| C2 | WARN | missing_sim_country=3, mismatch_locale=0, mismatch_timezone=0, mismatches=0 |
| C3 | PASS | checked=3, failed=0, missing=0 |
| C4 | WARN | attempts=3, distinct=2, errors=1, timeouts=0, data_available=false |
| C5 | WARN | samples=0 |

Cierre E-2 pendiente. C1 registra detecciones ajenas a Appium y el informe
no identifica sus paquetes concretos. C4 presenta un error sin desglose.
El criterio excepcional de SIM no aplica a este resultado.

Diagnostico: runs/e2_route_sync_20261109T153808213259Z.json y
runs/e2_route_sync_20261109T153848929294Z.json.
Evidencia: runs/farm_preflight_farm-8c8906b947064cb98b5fea95470110ab.json.
Traza: runs/e2_farm_route_trace_20261109T153911894998Z.json.

### Limpieza C1 y preflight detenido en el proxy (2026-11-09 UTC)

Base c05ef66. El inventario de paquetes identifico un unico nombre que
dispara C1, com.topjohnwu.magisk, instalado en p01, p02 y p03. El contador
negative_automation_apps=3 corresponde a tres placas, con el mismo paquete
en cada una. El paquete ya figuraba en la limpieza anterior. Su presencia
actual no permite distinguir reinstalacion de limpieza incompleta.

Se verifico la identidad fisica antes de cada retirada. En las tres placas
el paquete era de terceros, sin coincidencia en la lista de propietarios
ni como componente administrador en la politica del dispositivo. Se hizo
una desinstalacion por placa y pm list packages confirmo su ausencia.
El detector C1 quedo sin coincidencias en la lectura posterior.

El unico preflight real posterior termino con codigo 4 y decision
precheck_failed. La traza registro stage=ipify, cause=timeout_ipify y
error_type=TimeoutError en la consulta por navegador del proxy. El informe
registra synthetic=false y verdicts=[]. C1-C5 quedan sin reevaluar. E-2
sigue abierto hasta obtener un resultado de granja aceptable.

Inventario: runs/e2_c1_packages_20261109T154634680746Z.json.
Retirada: runs/e2_c1_cleanup_20261109T154634680746Z.json.
Preflight: runs/farm_preflight_farm-98b79cc253b54adc92145b9628f27388.json.
Traza: runs/e2_farm_cleanup_trace_20261109T154657214396Z.json.

### Resiliencia del preflight y cierre E-2 (2026-11-09 UTC)

Base 2df9ae3. La consulta de IP publica por el navegador prueba icanhazip,
ipify e ifconfig.me en orden, con un maximo de tres intentos. Cada intento
tiene un plazo total de 15 segundos para navegar y leer el cuerpo. La
respuesta se valida como IP publica de la misma familia que la consulta
directa. Se conserva la comprobacion de fuga y la validacion GeoIP.

La prueba unitaria simula timeout del primer endpoint y respuesta JSON del
segundo. Las pruebas de fallo total verifican el limite de tres intentos.
El preflight real de las tres placas se ejecuto una vez. El primer endpoint
respondio. El informe registra synthetic=false, codigo 0 y decision
proceed_with_warnings.

| Condicion | Estado | Contadores principales |
|---|---|---|
| C1 | WARN | checked=3, negative_automation_apps=0, negative=0, integrity_probe_errors=3 |
| C2 | WARN | missing_sim_country=3, mismatch_locale=0, mismatch_timezone=0, mismatches=0 |
| C3 | PASS | checked=3, failed=0, missing=0 |
| C4 | PASS | attempts=3, distinct=3, errors=0, timeouts=0 |
| C5 | WARN | samples=0 |

E-2 cerrado, listo_para_E3. El fallback se acredito en pruebas unitarias.
La corrida real acredito la primera opcion y el preflight completo.

Evidencia: runs/farm_preflight_farm-f5f635c5aeaa4ed690e1c640b207c299.json.
Traza: runs/e2_preflight_final_20261109T155508509050Z.json.

### E-3: Primera corrida fisica real

Fecha UTC: 2026-11-09. Base: e26997c. Estado: bloqueado en admision.
ADB 5037 confirmo la identidad fisica de las tres placas del CSV mediante
el mapa DPAPI. Panda asigna numeros distintos a p01 y p02. El flujo nativo
exige coincidencia por numero Panda e identidad fisica.

| plate_id | Panda CSV | Panda vivo | completed | duration | incidents |
|---|---|---|---|---|---|
| p01 | 13 | 07 | No evaluado | No medida | No evaluados |
| p02 | 15 | 06 | No evaluado | No medida | No evaluados |
| p03 | 22 | 22 | No evaluado | No medida | No evaluados |

El prechequeo de SQLite detecto que telemetria_panda.db carece de
auditorias_panda y que telemetry_qa.db, requerida para eventos_ia_qa,
no existe en la raiz del framework. Ambas tablas son obligatorias para
la auditoria nativa.

Intentos de corrida: 0. Retencion solicitada: 12 segundos, sin medicion.
Sin Vision, sin acciones de la corrida en placas. El playbook E-3 requiere
observacion del operador para acreditar incidentes sin Vision.

Evidencia: runs/e3_execution_20261109T160055497743Z.json.

#### Sincronizacion de numeros visuales Panda

Fecha local: 2026-11-09, America/Guatemala. Las tres rutas estaban activas
en el servidor ADB 5037. El mapa DPAPI, la identidad fisica leida de Android
y el inventario vivo de Panda coincidieron para las tres placas.

| Placa | Panda anterior | Panda verificado | device_ref |
|---|---|---|---|
| p01 | 13 | 07 | Confirmado |
| p02 | 15 | 06 | Confirmado |
| p03 | 22 | 22 | Confirmado |

El CSV se valido con tres filas vinculadas. El preflight sintetico termino
con codigo 0 sobre SQLite temporal. La verificacion de rutas fue en vivo
y separada del preflight sintetico.

La preparacion de auditorias_panda y eventos_ia_qa se valido sobre copias.
El plan admite tres inserciones por tabla. La inicializacion de los esquemas
operativos sigue pendiente para la etapa autorizada de E-3.

Evidencia: runs/e3_admission_plan_20261110T033642760729Z.json.

#### Revalidacion dinamica del inventario

Fecha local: 2026-11-09, America/Guatemala.
Los IDs visuales de Panda son dinamicos. El CSV se sincroniza por identidad fisica antes de cada corrida.
La lectura en vivo de Panda y ADB confirmo 07, 06 y 22 para p01, p02 y p03,
en el orden del mapa DPAPI. El CSV ya coincidia con esa lectura.

El preflight real de confirmacion termino con codigo 0 y decision
proceed_with_warnings. La persistencia se hizo en una copia SQLite dentro
de runs/ y los hashes operativos permanecieron iguales.
Evidencia: runs/e3_resync_20261110T034342397408Z/admission.json y preflight.json.

### E-3: Primera corrida fisica

Fecha local: 2026-11-09, America/Guatemala. Una ejecucion, un ciclo,
retencion solicitada de 12 segundos y concurrencia 1. La captura y el
procesamiento de cada placa comparten el semaforo. La prueba con stubs
observo una sola captura activa y verifico la cancelacion antes del gesto.

El proceso termino en 27.982 segundos con codigo 0 y completed=true.
Panda acepto la orden de desplazamiento para 07, 06 y 22. SQLite registro
tres filas en auditorias_panda y tres en eventos_ia_qa. Ambas auditorias
por clave y run_id pasaron. La llamada al modelo se omitio en las tres
placas. La muestra de farm_stage_metrics conserva los tres contadores NULL.

El operador confirmo que observo las tres pantallas durante la corrida.
En 07, 06 y 22 vio reproduccion continua de videos, sin captchas,
softblocks ni deslogueos observados. Los contadores automaticos permanecen
en NULL porque la corrida fue sin Vision.

Decision: E-3 cerrado, listo_para_E4.

Pytest y unittest terminaron con codigo 0 (541 pruebas en unittest).
Las suites conservaron los hashes de las bases operativas y los logs.
Evidencia: runs/e3_native_20261110T035637036746Z/verified.json y suites.json.

### E-4: Integracion de Vision

Fecha local: 2026-11-09, America/Guatemala. Una corrida de 41.027 segundos,
codigo 0, un ciclo, concurrencia 1 y tres analisis validos con gpt-4o-mini.
OpenAI respondio HTTP 200 a las tres solicitudes. El esquema JSON valido
las tres respuestas. Las capturas analizadas no mostraron captchas,
softblocks ni deslogueos. La observacion corresponde a esas tres capturas.

| Placa | Analisis | Tokens entrada | Tokens salida | USD estimado |
|---|---|---|---|---|
| p01 | 1 | 37148 | 154 | 0.0056646 |
| p02 | 1 | 37148 | 107 | 0.0056364 |
| p03 | 1 | 37148 | 112 | 0.0056394 |
| Total | 3 | 111444 | 373 | 0.0169404 |

Tarifas USD por millon de tokens: 0.15 entrada, 0.075 entrada cacheada y
0.60 salida. La API reporto cero tokens cacheados. Fuente:
https://developers.openai.com/api/docs/models/gpt-4o-mini

RateGate fijo 30 RPM, con un minimo de 2 s entre inicios. Los intervalos
medidos fueron 8.047 s y 5.656 s, sin solapamiento de solicitudes.
Ambas auditorias SQLite pasaron con tres inserciones cada una. La muestra
de etapa registro (0, 0, 0) a partir de los indicadores evaluados. C5 paso
al releer el historial. Los hashes protegidos se conservaron.

Pytest y unittest terminaron con codigo 0. Unittest ejecuto 541 pruebas.
Las suites conservaron los hashes de las bases y los logs.
Decision: E-4 cerrado, listo_para_E5_y_Escalado.
Evidencia: runs/e4_native_20261110T044222250803Z/verified.json y suites.json.

### E-5 y E-6: Validacion local y escalado simulado

Fecha local: 2026-11-10, America/Guatemala.
El panel FastAPI se inicio en 127.0.0.1:8000. La prueba HTTP obtuvo 200
en /, /api/status y /api/evidence. El estado inicial fue idle y el panel
expuso solo las acciones de verificacion sintetica y parada.

La prueba CLI con historial temporal aprobo la promocion 3 -> 10 y la
evaluacion de 10 muestras limpias en etapa 10. --stage-limits exigio las
10 muestras y bloqueo la promocion con 9. Un captcha en etapa 3 devolvio
codigo 2, decision abort y next_stage=null. Los planes mantuvieron
executes_next_stage=false y el stub de ejecucion nativa no fue invocado.

Se cerro explicitamente la conexion SQLite de lectura del plan para
liberar el archivo al terminar, incluido en Windows.
Pytest y unittest terminaron con codigo 0. Unittest ejecuto 543 pruebas.
Las suites conservaron los hashes de las bases y los logs.
Evidencia: runs/e5_e6_20261110T150824023301Z/http_smoke.json y suites.json.

### Bloqueo de conectividad externa con Proxy-Cheap (E-2)

Fecha UTC: 2026-11-08T05:39:27+00:00. Commit base: 2d7b42d.
Configuracion actual verificada en memoria: host thehub.proxy-cheap.com,
puerto 8080, protocolo HTTP. Usuario y password no se registran.
Evidencia previa: DNS correcto, tres timeouts TCP, handshake SOCKS5 y
autenticacion no evaluados al no establecer TCP, curl HTTP 000 con salida 28
y timeout de veinte segundos. Sin nuevas pruebas de red en esta entrega.

El operador reporta confirmacion del panel: HTTP, host y puerto coincidentes,
credenciales correctas, generador de comandos consistente con la prueba,
tiempo online 0% y limite alcanzado 0 veces. No se inspecciono el panel desde
el agente: es evidencia declarada por el operador. El 0% no demuestra ausencia
historica de conexiones; hubo verificaciones exitosas anteriores en el proyecto.

Clasificacion: red_aun_fallando. No se acredita bloqueo_proveedor de forma
concluyente; falta distinguir ruta, filtrado remoto o indisponibilidad.
Accion: ticket al proveedor y contraste desde otra red. El ticket exacto pedido
se preparo sin enviarlo: runs/e2_proxy_support_ticket_20261108T053927044934Z.txt.
Resumen: runs/e2_proxy_blocker_20261108T053927044934Z.json.

El ticket conserva el texto solicitado. Salvedades: no hay captura que pruebe
envio de CONNECT durante el timeout, y las versiones de SO/curl del texto no
se verificaron independientemente. No se presenta esa redaccion como hallazgo
tecnico adicional ni se incluyen credenciales o IP publica.

Red alternativa: un hotspot movil existente permite repetir DNS/TCP/auth/CONNECT
sin comprar recursos. Un VPS existente tambien sirve si el operador ya tiene
acceso autorizado, pero no replica la salida de este host. No se confirmo
disponibilidad de ninguno ni se aprovisiono o uso infraestructura externa.
Si otra red funciona y esta no, comparar ruta y filtrado por origen; si ambas
fallan, aportar ambos resultados a soporte sin asumir causa exclusiva.

E-2 permanece bloqueado; pendiente enviar el ticket manualmente y elegir una
red alternativa disponible. Sin preflight, ADB, pantallas o cambios de .env.

Validacion: 499 pytest y 28 subtests PASS; 497 unittest PASS en repeticion.
La primera suite unittest fallo en test_rate_gate_spaces_request_starts por
su umbral temporal; se conservo el log y no se modifico codigo ni tests.
Credenciales aisladas, guardia sin accesos y hashes G/Q antes/despues identicos.

### Inventario por identidad fisica

La API de 3CFarmBox documenta `updateDevices` con `name` y `sort`.
El panel usa alias locales por `device_ref`. No se enviaron cambios a Panda.
Ejecutar `python -m core.device_aliases` coteja el inventario con el mapa
DPAPI e importa los alias faltantes a `data/device_aliases.db`. Los alias
personalizados existentes se conservan. `GET /api/status` consulta la tabla
`device_aliases` y muestra cada alias junto a su etiqueta de inventario.

El flujo combinado toma el numero visual vigente de la fila vinculada por
serial fisico y transporte. Un vinculo ausente, ambiguo o con otra ruta
impide admitir el lote. El CSV conserva su valor anterior como referencia.

### Numeros fijos en Panda

Desde la raiz operativa, ejecutar
`python -m scripts.aplicar_aliases_panda --apply` al iniciar el laboratorio,
despues de que Panda muestre las tres placas. El comando aplica los alias
SQLite y los numeros 07, 06 y 22 via `updateDevices`. Cruza `device_ref`
con DPAPI y `onlySerial`, y envia cada cambio al transporte vigente.
Un numero ocupado o una identidad ambigua impiden la operacion.
El comando relee Panda para confirmar cada cambio y omite los ya aplicados.
Ejecutar sin `--apply` para comprobar la asignacion tras una reconexion.

### Preparacion del escalado a diez placas

El flujo combinado verifica desde cada Android que puede llegar a
`ipv4.icanhazip.com`. Usa HTTPS con curl cuando esta disponible y ping
como prueba de conectividad basica en su ausencia. El panel indica el metodo.
Una placa sin identidad o red verificable queda excluida. Si el lote queda
por debajo de la cuota, no entra a Vision.

`--prepare-devices --device-timezone Europe/Madrid` abre TikTok en las
placas vinculadas, comprueba el foco y coteja region y zona horaria.
Solo aplica una zona manual si Android ofrece el comando y el dispositivo
ya admite zona manual. Los ajustes no confirmados se marcan en el panel.
`--ready` requiere que el operador confirme el feed de prueba.
Los candidatos privados se guardan en un CSV bajo `runs/`.

El panel muestra la ultima comprobacion por placa y un coste estimado de
Vision a partir del uso informado. Conserva la evidencia bajo Avanzado.
Un incidente visual detiene la cola y queda registrado en las metricas
de etapa para bloquear la promocion.

C1 registra Magisk, su daemon y el shell con UID privilegiado como WARN
en los preflights reales. Estas senales se conservan en la evidencia.
Emulacion, automatizacion bloqueante o una comprobacion de integridad
negativa siguen produciendo FAIL. La politica de aborto por WARN se respeta.
