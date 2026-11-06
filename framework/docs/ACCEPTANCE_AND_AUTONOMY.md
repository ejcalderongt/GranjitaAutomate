# Marco de aceptacion y autonomia

El plan vigente y el estado de cada etapa se consultan en [PLAN_ETAPAS.md](PLAN_ETAPAS.md).
El contrato del futuro panel se aplica segun [LAB_UI.md](LAB_UI.md).

## Seccion 1. Parametros de aceptacion

Cada trabajo encolado por el agente debe evaluarse contra estos parametros, en este orden. Un trabajo que no cumple un parametro duro se descarta y se reporta. Un trabajo que no cumple un parametro blando se acepta como parcial y se continua con la siguiente etapa o con reajuste.

### 1.1 Parametros duros (descartan el trabajo si fallan)

- **P-1 Seguridad del codigo existente.** No se rompen tests existentes. Si un test existente falla por causa del trabajo nuevo, el trabajo se descarta y se rehace.
- **P-2 Alcance cerrado.** El trabajo no toca archivos fuera del alcance declarado en el prompt que lo encola. Si toca alguno, se descarta y se rehace con alcance corregido.
- **P-3 Invariantes de datos.** No hay corrupcion de bases protegidas, ni cambios en tablas fuera de las excepciones declaradas, ni perdida de filas historicas.
- **P-4 Invariantes de red y dispositivo.** Ninguna accion sobre red o dispositivos fuera de las autorizadas en el prompt original.
- **P-5 Trazabilidad.** Cada accion deja evidencia en `runs/` o en el commit, segun corresponda. Sin evidencia, el trabajo no cuenta como completado.
- **P-6 Encaje con el objetivo final.** El trabajo, directa o indirectamente, acerca el sistema al objetivo final declarado: laboratorio controlado con UI, entregable funcional, flujos validados sobre dispositivos fisicos y red residencial, integracion con modelo de vision y escalado por etapas.
- **P-7 Codificacion.** ASCII puro en artefactos. Sin emojis, sin caracteres fuera de 0x20-0x7E en codigo, docs, logs, reasons ni commits.
- **P-8 Sin dependencias nuevas no autorizadas.** Si el trabajo requiere una dependencia nueva, se detiene y consulta antes de instalarla. La instalacion de dependencias ya declaradas en el proyecto si esta autorizada por este marco.
- **P-9 Ejecucion controlada.** Si el trabajo requiere ejecutar programas, lo hace con timeouts, con captura de stdout y stderr, con codigo de salida y con evidencia. Sin bucles infinitos, sin reintentos ilimitados.

### 1.2 Parametros blandos (permiten continuar con aviso)

- **P-10 Cobertura.** Un trabajo que aporta cobertura parcial se acepta si la cobertura nueva es proporcional al esfuerzo invertido. Se puede volver a ampliar en una etapa posterior.
- **P-11 Rendimiento.** Un flujo lento pero correcto se acepta si cabe en el presupuesto de tiempo de la etapa. Si no cabe, se reajusta y se vuelve a intentar.
- **P-12 Estetica de UI.** Una UI funcional pero no refinada se acepta como entregable provisional. El refinamiento se encola como etapa posterior.
- **P-13 Cobertura de casos borde.** Un trabajo que no cubre todos los casos borde se acepta si cubre los caminos principales y los casos borde quedan identificados como pendientes.

### 1.3 Criterios de continuidad, reajuste y descarte

- **Continuar** si todos los parametros duros pasan y al menos el 80 por ciento de los parametros blandos aplicables estan en verde.
- **Reajustar** si un parametro duro falla por causa corregible dentro del mismo alcance (por ejemplo, un test roto por un detalle de implementacion, no por diseno). El agente rehace la parte afectada, sin volver a pedir confirmacion.
- **Descartar** si un parametro duro falla por causa de diseno, si el alcance se desvio, o si se detecta riesgo de seguridad o de datos. El agente descarta la rama de trabajo, reporta el descarte con evidencia, y pasa a la siguiente tarea del backlog.
- **Volver a encolar** si el trabajo fue rechazado por falta de informacion. El agente pide la informacion minima al humano y pausa esa rama.

### 1.4 Presupuesto de ejecucion por etapa

Cada etapa encolada tiene un presupuesto maximo de:

- iteraciones de agente por etapa (default 3),
- tiempo total de ejecucion (default 60 minutos por etapa),
- tamano maximo de evidencia acumulada por etapa (default 50 MB en `runs/`).

Si la etapa excede el presupuesto, el agente se detiene, consolida lo que tenga y reporta estado parcial. No continua sin autorizacion humana.

## Seccion 2. Politica de autonomia

A partir de este marco, el agente orquestador tiene autoridad para:

A-1. **Instalar dependencias ya declaradas en el proyecto** si no estan instaladas en `.venv`. Sin instalar dependencias nuevas no declaradas.

A-2. **Ejecutar programas del propio repo**: `pytest`, `scripts/run_tests.py`, `main_panda_masivo.py` con `--help`, y las demas herramientas internas en modo lectura o dry-run.

A-3. **Crear y actualizar archivos dentro del alcance del prompt** que lo encola, sin pedir confirmacion intermedia, siempre que cumplan P-1..P-9.

A-4. **Commitea y pushear** cada etapa cerrada en verde con mensaje ASCII y push a `dev2026-work`, sin pedir confirmacion, siempre que la suite este en verde.

A-5. **Volver a encolar** una etapa fallida una sola vez si el fallo es reajustable, sin pedir confirmacion. Una segunda vez requiere autorizacion humana.

A-6. **Encadenar etapas del backlog** dentro de una misma sesion de orquestacion, sin mensajes intermedios, siempre que cada etapa termine en commit o en descarte con evidencia.

A-7. **Detenerse y consultar** solo en los bloqueantes duros definidos en cada prompt y en los siguientes casos universales:

- cambios en `.env`,
- ampliaciones de contrato de `ProxyManager` o de servicios externos,
- cambios en `decide()`, `EXIT_*`, `PANDA_POLICY_*`,
- acciones de escritura sobre dispositivos fuera de las autorizadas,
- clasificacion de Appium como residuo,
- necesidad de tocar `core/browser.py`, `main_panda.py`, `tiktok_warmer/core/socks_bridge.py`, `config/proxies.py` fuera de la superficie publica acordada,
- cualquier intento de ejecutar Vision, calentamiento o lote de 34 sin autorizacion previa,
- riesgo de perdida de datos o de historia git.

## Seccion 3. Contrato de entregable funcional con UI

Un alcance se considera entregable funcional con UI cuando cumple todo lo siguiente:

E-1. **Interfaz operable.** Existe una UI que permite al operador iniciar, pausar, detener y observar el estado de las etapas del laboratorio.

E-2. **Estado observable.** La UI muestra, en tiempo real o por refresco, el estado de cada etapa: en curso, completada, abortada, con reasons humanos.

E-3. **Evidencia accesible.** La UI permite navegar a la evidencia de cada corrida: logs, JSON de resultados, hashes de invariantes.

E-4. **Acciones seguras.** La UI no permite ejecutar acciones que el agente no tenga autorizadas. Cada accion se valida contra las autorizaciones vigentes.

E-5. **Documentacion.** Existe un documento `docs/LAB_UI.md` que describe la UI, las acciones disponibles, las autorizaciones vigentes y como interpretar los estados.

E-6. **Suite en verde.** La suite cubre la UI y las acciones expuestas.

E-7. **Sin regresiones.** El flujo sin UI sigue intacto. La UI es un envoltorio del flujo, no una reimplementacion.

E-8. **Encaje con el objetivo final.** La UI sirve al objetivo declarado del laboratorio controlado con flujos validados sobre dispositivos fisicos, red residencial, integracion con modelo de vision y escalado por etapas.

## Seccion 4. Backlog derivado de este marco

Del contrato de entregable funcional se derivan las siguientes etapas, encolables por el agente:

- **E-A. Hito 3 corregido.** El que ya esta definido. Se ejecuta primero, con el marco aplicado.
- **E-B. Primer preflight real sobre 3 placas del CSV.** Con mapeo DPAPI persistido, alineacion locale/timezone y limpieza autorizada de paquetes ya aprobada. Cierra con evidencia de C1..C5 en WARN o PASS aceptable.
- **E-C. Primera corrida real controlada sin modelo de vision.** 3 placas, 1 ciclo, `--execute-read-only --ready --concurrency 1 --hold-seconds 12`. Cierra con cero incidentes o con informe de incidentes.
- **E-D. Integracion del modelo de vision** con `RateGate` y `AsyncOpenAI`. Cierra con `farm_stage_metrics` poblado con muestras completas y C5 en PASS.
- **E-E. UI minima operativa.** Panel web local que permite iniciar, pausar, detener, observar estado y navegar evidencia. Cumple E-1..E-8.
- **E-F. Escalado por etapas.** `--stage`, `--stage-limits`, criterios de exito por etapa, abort automatico. Cumple el objetivo de escalar de 3 a 10 a 34 sin intervencion humana por paso.
- **E-G. Backlog de mejoras de laboratorio.** Todo lo que surja durante E-A..E-F y cumpla el objetivo final, priorizado por el agente segun P-6.

Cada etapa encolada hereda el marco de este documento y no requiere re-discutirlo.
