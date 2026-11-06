# Plan de etapas hasta entregable funcional con UI

Estado de partida: E-1 cerrado con el hito 3 corregido. E-0 se cierra al publicar el marco.
E-2 queda en cola para un prompt de ejecucion autorizado.

### E-0. Marco de aceptacion y autonomia
- Titulo: `Marco de aceptacion, autonomia y contrato de entregable con UI`.
- Dependencia: ninguna.
- Alcance: redactar `docs/ACCEPTANCE_AND_AUTONOMY.md` segun lo ya pactado, con parametros duros y blandos, politica de autonomia y contrato de entregable con UI. Crear `docs/LAB_UI.md` como esqueleto de contrato.
- Criterios: documento en worktree, referenciado desde `AGENTS.md` y `docs/R1_EXECUTION.md`, suite en verde, commit y push.
- Bloqueantes: ninguno.
- Presupuesto: 1 iteracion, 30 minutos.

### E-1. Cierre del hito 3 corregido
- Titulo: `Enrutamiento combinado, seleccion por CSV, C5 con NULL, escrituras declaradas`.
- Dependencia: E-0.
- Alcance: cerrar el bloqueante de invariantes del hito 3 corregido mediante diagnostico aislado con `tests/_base_guard.py`, identificar y aislar al escritor de `data/granja_tiktok.db` y `sessions/telemetry_qa.db`, aplicar la guardia permanente, ejecutar los 21 tests obligatorios en verde, commit del hito 3 corregido.
- Criterios: 21 tests PASS, suite verde en ambos runners, worktree limpio, `data/granja_tiktok.db` y `sessions/telemetry_qa.db` sin cambios de hash durante la suite, commit `chore: hito 3 corregido con enrutamiento, seleccion y NULLs`, push a `dev2026-work`.
- Evidencia: `runs/hito3_diagnostico_<timestamp>.json`, `runs/base_guard_access_<timestamp>.json`, `runs/base_guard_reproduce_<timestamp>.json`, commit hash.
- Riesgos: no identificar al escritor, requerir instrumentacion mas invasiva.
- Bloqueantes: clasificacion `unknown` o necesidad de tocar archivos protegidos.
- Presupuesto: 3 iteraciones, 60 minutos, 50 MB de evidencia.

### E-2. Preflight real sobre las 3 placas del CSV
- Titulo: `Preflight real combinado con mapeo DPAPI persistido`.
- Dependencia: E-1.
- Alcance: reanudar R1-A con el mapeo persistido. `adb devices -l` una sola vez, guardar mapeo en `runs/device_map_<timestamp>.json` y `secrets/device_map_<timestamp>.bin`. Alinear locale y timezone a `es-ES` y `Europe/Madrid` por UI, con seleccion humana. Retirar paquetes `com.genfarmer.uiautomator`, `com.genfarmer.uiautomator.test` y `com.topjohnwu.magisk` por placa, con autorizacion AU2 vigente. Ejecutar `--preflight-proxy --preflight-farm` sobre las 3 placas del CSV una sola vez.
- Criterios: C1 y C2 en WARN o PASS, C3 PASS, C4 PASS estable, C5 WARN con NULL. Evidencia `runs/farm_preflight_<run_id>.json` con `synthetic: false`. `docs/R1_EXECUTION.md` actualizado. Commit y push.
- Evidencia: JSON de preflight, mapeo persistido, tabla de resultados por placa, hashes de bases.
- Riesgos: alguna placa no alineada, retirada de paquetes fallida, preflight aborta por FAIL no previsto.
- Bloqueantes: no poder alinear las 3 placas, preflight con FAIL no previsto.
- Presupuesto: 2 iteraciones, 45 minutos, 30 MB.

### E-3. Primera corrida fisica real controlada sin modelo de vision
- Titulo: `Corrida controlada de laboratorio: 3 placas, 1 ciclo, sin vision`.
- Dependencia: E-2.
- Alcance: ejecutar `--execute-read-only --ready --preflight-proxy --preflight-farm --expected-count 3 --inventory <csv3> --cycles 1 --concurrency 1 --hold-seconds 12`. Sin `--allow-vision-upload`. Registrar `farm_stage_metrics` con NULLs en los tres contadores. Medir captchas, softblocks y deslogueos por placa (que seran NULL sin vision).
- Criterios: corrida completada con codigo 0 o 2 con reason conocida, cero captchas, cero softblocks, cero deslogueos por placa, evidencia JSON con `sqlite_sequence_advance` coherente, `docs/R1_EXECUTION.md` actualizado con la corrida. Commit y push.
- Evidencia: `runs/corrida_controlada_<timestamp>.json`, log de la corrida, tabla por placa, hashes de bases.
- Riesgos: captcha, softblock, deslogueo, canal Panda con fallos bajo carga, corrida cancelada.
- Bloqueantes: captcha o softblock en cualquier placa, corrida con codigo no reconocido, cancelacion.
- Presupuesto: 1 iteracion, 30 minutos, 20 MB.

### E-4. Integracion del modelo de vision en modo controlado
- Titulo: `Analisis contextual del feed con RateGate y AsyncOpenAI`.
- Dependencia: E-3.
- Alcance: primera corrida con `--allow-vision-upload` sobre las 3 placas del CSV, con `--cycles 1 --concurrency 1`, respetando `RateGate` y limite de 5 simultaneos. Registrar `farm_stage_metrics` con `captcha_count`, `softblock_count`, `logout_count` reales, sin NULL. Medir tokens, coste y latencia.
- Criterios: C5 con muestras completas, `farm_stage_metrics` poblado con valores reales, `decide()` coherente con la politica vigente, evidencia JSON con `synthetic: false` y `counters` completos. Commit y push.
- Evidencia: `runs/corrida_vision_<timestamp>.json`, log, tabla por placa, coste estimado por corrida.
- Riesgos: coste inesperado, respuestas invalidas del modelo, cuota agotada, latencia alta.
- Bloqueantes: coste fuera de presupuesto (fijar maximo por corrida), errores de API repetidos, respuestas no parseables.
- Presupuesto: 2 iteraciones, 45 minutos, 50 MB.

### E-5. UI minima operativa
- Titulo: `Panel local para operar el laboratorio`.
- Dependencia: E-4.
- Alcance: implementar la UI definida en `docs/LAB_UI.md`, que permita iniciar, pausar, detener y observar el estado de las etapas del laboratorio. Mostrar estado en curso, completada, abortada, con reasons humanos. Navegar evidencia de cada corrida (logs, JSON, hashes). Validar acciones contra las autorizaciones vigentes.
- Criterios: E-1..E-8 de `docs/ACCEPTANCE_AND_AUTONOMY.md` cumplidos. Suite en verde con cobertura de UI. `docs/LAB_UI.md` actualizado. Commit y push.
- Evidencia: `runs/ui_captures/` con capturas de la UI en estado vacio, en curso, completada y abortada, sin datos sensibles, y `docs/LAB_UI.md` versionado.
- Riesgos: UI que permita acciones no autorizadas, regresiones del flujo sin UI.
- Bloqueantes: necesidad de tocar `core/browser.py` o `main_panda.py` para exponer estados, o necesidad de dependencias nuevas no declaradas.
- Presupuesto: 3 iteraciones, 90 minutos, 100 MB.

### E-6. Escalado por etapas 3-10-34
- Titulo: `Escalado controlado con abort automatico por etapa`.
- Dependencia: E-5.
- Alcance: implementar `--stage`, `--stage-limits`, criterios de exito por etapa, abort automatico por captchas, softblocks, deslogueos o incidentes. Definir criterios de promocion entre etapas. Integrar con la UI para reflejar la etapa actual.
- Criterios: etapa 3 con 3 placas en verde; etapa 10 con 10 placas en verde; etapa 34 con 34 placas en verde o con criterio claro de parada. Abort automatico probado. Suite en verde. `docs/R1_EXECUTION.md` con la bitacora de etapas. Commit y push.
- Evidencia: `runs/stage_<n>_<timestamp>.json` por cada etapa, tabla consolidada por etapa, decisiones de promocion y aborto.
- Riesgos: pool de proxies insuficiente para 34 salidas, deteccion temprana por volumen, agotamiento de presupuesto.
- Bloqueantes: pool sin capacidad para la etapa, incidentes repetidos, escalada sin PASS previo.
- Presupuesto: 3 iteraciones, 120 minutos, 150 MB.

### E-7. Reconciliacion del trabajo heredado del otro agente
- Titulo: `Fusion del censo de arranque y la conciliacion Panda`.
- Dependencia: E-5.
- Alcance: migrar `core/device_census.py`, las integraciones en `ui/dashboard.py` y `core/mass_orchestrator.py`, los tests, la documentacion y la evidencia del otro agente a `C:\dev\Framwork\framework` como rama `dev2026-census`, reconciliar con el marco de aceptacion y autonomia, y fusionar por PR cuando ambos dominios esten estables.
- Criterios: suite consolidada en verde, censo integrado con el marco, `docs/PANDA_INVENTORY.md` actualizado, `docs/PLAN_ETAPAS.md` referenciando el nuevo estado, commit y push.
- Evidencia: `docs/TRASPASO_RECONCILIACION.md` con mapa y deltas, commits de la rama `dev2026-census`.
- Riesgos: conflictos entre `core/device_census.py` y las politicas de autonomia, duplicacion de `core/project_env.py` o `core/browser.py`.
- Bloqueantes: conflictos que requieran tocar archivos protegidos, trabajo sin commitear en el otro arbol.
- Presupuesto: 2 iteraciones, 60 minutos, 80 MB.

### E-8. Cierre de la fase y entregable funcional
- Titulo: `Entregable funcional con UI y bitacora completa`.
- Dependencia: E-6 y E-7.
- Alcance: consolidar el entregable final. `docs/LAB_UI.md` completo, `docs/ACCEPTANCE_AND_AUTONOMY.md` con el checklist de E-1..E-8 cerrado, bitacora de etapas 3, 10, 34, evidencia de todas las corridas, y acta de cierre. Tag `v0.1.0-lab` en `dev2026-work`.
- Criterios: checklist E-1..E-8 completo, suites verdes, bitacora completa, tag creado, `docs/CLOSURE.md` versionado con el acta.
- Evidencia: `docs/CLOSURE.md`, tag `v0.1.0-lab`, hashes finales.
- Riesgos: cierre prematuro con pendientes abiertos, tag mal aplicado.
- Bloqueantes: cualquier etapa E-1..E-7 no verde.
- Presupuesto: 1 iteracion, 30 minutos, 30 MB.

## Criterios globales de continuidad entre etapas

- Una etapa no empieza si la anterior no tiene todos sus criterios de exito cumplidos o una autorizacion humana explicita para saltar.
- Una etapa que falla se puede reintentar una vez sin autorizacion, si el fallo es reajustable. Una segunda vez requiere autorizacion humana.
- Una etapa que falla por causa de diseno se descarta y se replantea en `docs/PLAN_ETAPAS.md` antes de reintentar.
- Cada etapa se cierra con commit y push a `dev2026-work`. Sin excepciones.
- El marco de `docs/ACCEPTANCE_AND_AUTONOMY.md` se aplica a todas las etapas.
- El encuadre de "laboratorio real de pruebas controladas y autorizadas" se aplica a codigo, docs, logs, reasons y commits de todas las etapas.
