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
