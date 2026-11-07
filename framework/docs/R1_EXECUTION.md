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
