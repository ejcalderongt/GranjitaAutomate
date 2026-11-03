# Metadatos y decisiones del feed web

`core/scraper.py:extraer_contexto_video` devuelve autor, descripcion y
sonido_original. Cada campo tiene su propio manejo de errores y limite de
longitud. En el orquestador se usa el contenedor activo, nunca todo el feed.
Los selectores son candidatos: deben validarse en el DOM de la sesion real.
No se afirma que estos selectores hayan sido verificados contra TikTok vivo.
Los archivos config/web_selectors.mobile.json y web_selectors.example.json
admiten un objeto metadata con selectores locales al contenedor activo.

`core/ai_agent.py:evaluar_con_openai` usa gpt-4o-mini con JSON Schema estricto
y valida los tipos, campos, coherencia de comentarios y longitud de hasta 8
palabras en minusculas. La instruccion solicita maximo un emoji; la validacion
local no cuenta grafemas emoji. Metadatos sin descripcion no generan una
consulta: se devuelven recomendaciones false. Rechazos, respuestas truncadas,
errores y JSON invalido no habilitan acciones. El contexto del DOM va en el
mensaje user; las reglas permanecen en system. No se analiza imagen ni sonido.

El flujo Android conserva su esquema anterior. En web, comentario se adapta
internamente a texto_comentario para los ejecutores existentes. compartir
solo se registra; no hay ejecutor de compartidos. La evidencia post_decision
se captura antes de habilitar acciones; se revalidan contexto e identidad
del video. Sin --execute se conserva el modo sin interacciones sociales.

## Historico local

Cada cuenta y ejecucion escribe:

`logs/<account_id>/decisiones-<run_id>.jsonl`

Cada linea incluye schema_version, timestamp UTC, account_id, run_id,
cycle_id y evento. Los eventos context y decision conservan metadatos,
recomendacion JSON, modelo, version del prompt, latencia y disponibilidad de
evidencia. ai_error conserva tipo de error, no textos de excepciones con
posibles secretos. Los eventos de clic/envio no prueban aceptacion del servidor.
Los registros se escriben y sincronizan a disco antes de continuar; un fallo
de persistencia no permite proseguir con acciones sin auditoria. No es una
cadena criptografica de custodia ni una transaccion con TikTok.

No se incluyen claves API, contrasenas, cookies ni configuracion del proxy.
El texto publico del video, autor y comentario si quedan en el historico local;
logs/ esta excluido de Git. El operador controla su retencion y acceso.
El esquema de seleccion y reservas del pool no se modifica; los endpoints
rotativos siguen requiriendo una configuracion de salida acorde al supervisor.

## Resumen

Desde C:\dev\Framwork\framework:

```powershell
Get-ChildItem .\logs -Recurse -Filter 'decisiones-*.jsonl'
.\.venv\Scripts\python.exe scripts/resumir_decisiones.py RUTA_ABSOLUTA_DEL_HISTORICO
```

El resumen cuenta recomendaciones de likes, comentarios y compartidos,
comentarios identicos repetidos, errores IA, lineas invalidas y latencia media.
No asigna una puntuacion de autenticidad ni certifica entrenamiento de cuenta.
Las pruebas usan respuestas simuladas; no hubo una ejecucion de feed real ni
una consulta de pago a OpenAI durante esta integracion.

Formato de salida verificado con OpenAI Docs:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat

Ruta async opcional y contratos: ver ASYNC_FEED.md.
