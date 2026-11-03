# Feed web asíncrono

Los módulos síncronos existentes permanecen compatibles. La ruta nueva se
activa con --web-async en el mismo supervisor de cuentas:

```powershell
.\.venv\Scripts\python.exe main.py --web-accounts config/web_accounts.json --web-selectors config/web_selectors.mobile.json --web-engine patchright --web-async --web-warmup --cycles 1
```

El comando requiere cuentas, proxies y selectores previamente configurados.
No añade --execute: evalúa y avanza sin interacciones sociales. Para login
manual se mantiene --web-login-only con ventana visible. El modo async exige
ciclos positivos; el modo de login manual espera el cierre del operador.
No se ejecutó este comando contra TikTok vivo durante la integración.

## Contratos

- `await core.scraper.extraer_contexto_video_movil(page, scope=active)` recibe
  un Page/Locator asíncrono. Devuelve autor, descripcion y sonido_original,
  con límites de tamaño y manejo independiente de errores por campo.
  No llama a screenshot, no descarga video ni lee otro contenedor del feed.
- `await core.ai_agent.evaluar_video_con_ia(datos, client=async_client)` usa
  gpt-4o-mini, temperatura 0.8 y JSON Schema estricto compartido con la variante
  síncrona. Valida booleanos, comentario coherente, hasta 8 palabras en
  minúsculas y 160 caracteres. Máximo un emoji se solicita en el prompt;
  no se cuenta localmente la composición Unicode de los emojis.
- La clave OpenAI se carga perezosamente desde el entorno del proyecto.
  No se crea un cliente al importar. El cliente prestado no se cierra;
  un cliente creado dentro de la función se cierra en async with.
- Ante timeout, error API, rechazo o JSON inválido devuelve todas las acciones
  false y comentario vacío. on_error recibe únicamente el tipo de error;
  el orquestador registra ai_error y decision_origin=fallback. La cancelación
  se propaga y no se transforma en una decisión.

## Orquestación y limpieza

core/async_web_orchestrator.py realiza lecturas DOM con await y usa
AsyncOpenAI. No ejecuta el cliente síncrono dentro del loop. La admisión
global conserva api_slots y api_rate de SQLite WAL: comparte límites con los
workers anteriores. Las operaciones SQLite y fsync del histórico se delegan
a threads; la red del cliente y el navegador es asíncrona.

El puente HTTP local a SOCKS5 conserva su propio loop independiente y puerto
dinámico. Las sesiones persistentes, el pool exclusivo y la cuarentena por
limpieza no confirmada siguen bajo el supervisor existente. En finally se
intenta cerrar contexto, runtime y puente aunque uno falle. Las reservas API
se liberan incluso al cancelar la consulta. El cliente OpenAI del worker se
cierra antes de desmontar navegador y puente. No se cambian sandbox ni TLS.

Las capturas de auditoría post_decision/post_swipe siguen separadas de la
extracción textual y no se envían a OpenAI. La ejecución de acciones requiere
--execute, evidencia y revalidación de metadatos. compartir sigue sin ejecutor.
Si falla IA se registra fallback sin acciones y se intenta continuar el feed.
Si no se confirma el cierre del panel de comentarios, se detiene la cuenta
en vez de arrastrar sobre un formulario pendiente.

Histórico: logs/<cuenta>/decisiones-<run_id>.jsonl. El resumen existente añade
fallbacks para distinguir errores de una recomendación válida de no actuar:

```powershell
.\.venv\Scripts\python.exe scripts/resumir_decisiones.py RUTA_DEL_HISTORICO
```

Pruebas: DOM real local con varios contenedores; extracción sin screenshot;
respuestas simuladas de IA, rechazo/timeout/JSON inválido, cancelación,
liberación de slots SQLite, continuidad del swipe y cierre de recursos.
Estas pruebas no validan los selectores contra la sesión viva de TikTok ni
acreditan acciones aceptadas por su servidor.

OpenAI Docs: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat
