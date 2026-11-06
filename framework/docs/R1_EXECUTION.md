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
