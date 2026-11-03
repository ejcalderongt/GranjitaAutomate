# Carga QA y telemetría SQLite

La ruta --web-async utiliza una pausa determinista, sin ruido de lectura ni
objetivo de ocultación. Para descripción y etiqueta de audio:

`programado = min(30, base + 0.05 * cantidad_de_caracteres)`

La base se configura con --web-load-base (0–30 segundos, predeterminado 6).
La pausa mide tiempo monotónico real; no acredita reproducción del video.
Un asyncio.Event despierta la espera directamente; señales compartidas de
threading/procesos se consultan cada 50 ms. Cancelar la Task propaga la cancelación.

```powershell
.\.venv\Scripts\python.exe main.py --web-accounts config/web_accounts.json --web-selectors config/web_selectors.mobile.json --web-engine patchright --web-async --web-load-base 6 --cycles 1
```

Requiere pool, cuentas y selectores validados. No se incluye --execute.
La retención QA sustituye la espera aleatoria previa en esta ruta async.
El main.py y el supervisor anteriores mantienen sus modos de compatibilidad.

## Tabla y fases

`core/telemetry.py` usa sqlite3 encapsulado en asyncio.to_thread. No requiere
aiosqlite: cada operación abre, confirma o revierte y cierra su conexión.
Archivo predeterminado: sessions/telemetry_qa.db, excluido de Git.
CLI alternativa: --web-telemetry-db RUTA. El supervisor inicializa una sola
vez antes de crear workers. La API directa sin ruta puede inicializar su esquema.

La tabla metricas_rendimiento mantiene una fila por (run_id, account_id, cycle_id)
mediante UPSERT: mapeo → retencion → analisis → pre_swipe → finalizado.
Se conserva el timestamp inicial y se actualiza actualizada_utc. Incluye
ciclo_numero, estado_ciclo, estado_retencion y swipe_estado. Las tablas
anteriores del ejemplo se migran de forma aditiva preservando sus filas legacy.

Mediciones:

- espera_dom_visible_ms: espera de visibilidad del selector activo. No es una
  medición completa del renderizado, reproductor ni descarga de video.
- latencia_dom_ms: duración de la extracción de metadatos.
- tiempo_retencion_programado_seg y tiempo_retencion_ejecutado_seg.
- latencia_openai_ms: tiempo del await del SDK, separado de la admisión global.
- latencia_admision_ms y latencia_ia_total_ms: cola/admisión y evaluación total.
  Si no hay consulta por contexto insuficiente, latencia_openai_ms queda NULL.
- duracion_total_ms: tiempo transcurrido del ciclo, no suma artificial de campos.

La fase pre_swipe se confirma antes de enviar el gesto. El estado final se
confirma después del gesto: no se declara terminado un ciclo antes de ejecutar
su última fase. El swipe utiliza el canal CDP del navegador; el puente proxy
transporta red y no recibe órdenes de interacción.

Estados: running, passed, failed y cancelled. Un error de temporización o
SQLite registra tipo/fase en el histórico JSONL y omite el avance sin auditoría;
el worker puede intentar el siguiente ciclo. Si SQLite está indisponible no se
simula que existe una fila final. La cancelación devuelve None al supervisor y
termina el bucle. No se transforma un timeout de OpenAI en una decisión válida.

## Privacidad y cierres

Esta tabla no guarda descripción, autor, audio, cookies, claves ni decisiones
de comentario. error_log conserva el tipo de error, nunca el mensaje crudo.
proxy_ip queda REDACTED; proxy_ref contiene una referencia hash, no la IP ni
usuario/contraseña en claro. Es pseudonimización técnica, no una garantía
criptográfica de anonimato. geo_provider queda UNKNOWN si no se consultó un
proveedor durante esa ejecución. Los históricos JSONL anteriores son distintos
y conservan su alcance documentado; no se modifican ni purgan automáticamente.

Las conexiones SQLite se cierran en finally por operación. El worker intenta
cerrar contexto, runtime y puente aunque otro cierre falle, libera slots API
y solo acredita limpieza si se confirma. No se fuerza una liberación de leases
cuando la limpieza falla. TLS y sandbox no se modifican.

Consulta local de ejemplo:

```sql
SELECT run_id, account_id, ciclo_numero, estado_ciclo, latencia_dom_ms,
       latencia_openai_ms, tiempo_retencion_ejecutado_seg, error_log
FROM metricas_rendimiento ORDER BY id DESC LIMIT 30;
```

Interfaz nativa: ver POC_UI.md.
