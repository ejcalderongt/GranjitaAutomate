# Análisis textual asíncrono

`core.ai_agent.analizar_contenido_tiktok_async` añade un contrato de tres campos
sin cambiar los contratos existentes del orquestador. Devuelve recomendaciones;
no ejecuta interacciones ni inicia navegadores.

La ruta web asíncrona ahora llama a esta función con `datos_video=metadata`,
descripción, run_id, account_id y cycle_id. Los adaptadores síncronos históricos
siguen disponibles. La ruta asíncrona ignora `execute=True`: solo analiza y
desplaza. Sin descripción omite tanto retención como consulta de IA. Los tests
inyectan clientes simulados; el uso normal con descripción consulta la API real.

Después de navegar a TikTok, POC y worker consultan el gestor de consentimiento
de cookies durante un máximo de cinco segundos. Solo acepta un botón inequívoco
dentro de un diálogo de cookies identificado. Un diálogo no reconocido requiere
intervención manual. No se gestionan login, CAPTCHAs ni permisos. El filtro
GeoIP EU continúa ejecutándose antes de navegar a TikTok: un fallo allí no
puede atribuirse al consentimiento del sitio.

El desplazamiento conserva el adaptador táctil CDP de QA; no se ha incorporado
GhostCursor ni un mecanismo para ocultar automatización. Se mantienen los
límites de ciclos, cancelación y cierre del supervisor existente.

```python
from core.ai_agent import analizar_contenido_tiktok_async

decision = await analizar_contenido_tiktok_async(
    html_del_video_activo, descripcion,
    run_id=run_id, account_id=account_id, cycle_id=cycle_id,
    db_path=telemetry_db,
)
```

La clave se carga de `.env` mediante el cargador existente. El cliente oficial
AsyncOpenAI se crea dentro del bucle del worker y se cierra al terminar. Puede
prestarse un cliente asíncrono con `client=...`; su cierre corresponde al llamador.
No ejecutar con `asyncio.run` desde el hilo de Tkinter: usar el worker existente.
El límite es 25 segundos sin reintentos automáticos. La cancelación explícita
se propaga al supervisor para ejecutar su `finally`.

Pasar solo HTML del contenedor activo previamente autorizado para análisis,
nunca documentos completos que puedan incluir datos privados. Se eliminan
atributos, scripts y formularios; esto no constituye un detector universal de
datos sensibles. El texto y la descripción se envían a OpenAI. El prompt no
atribuye una identidad humana ni una región al operador a partir del proxy.

La tabla aditiva `eventos_ia_qa`, en la misma SQLite WAL de QA, guarda identificadores,
modelo, timestamp UTC, estado, latencia y códigos de error. No guarda entradas,
comentarios, respuestas, credenciales ni mensajes de excepciones. Pasar el run_id
del supervisor; si se omite se genera uno para la llamada independiente.
La latencia mide la espera del cliente; si se presta un adaptador con admisión,
incluye esa espera. Las conexiones SQLite se abren y cierran en hilos auxiliares.

Timeout, error de API o respuesta inválida devuelven
`{"interactuar": false, "dar_like": false, "comentario": ""}`. Un fallo de
persistencia también descarta la recomendación y registra un aviso en consola;
no se afirma que un evento quedó auditado si SQLite no permitió escribirlo.
Los emojis compuestos con varios pictogramas se rechazan conservadoramente.
