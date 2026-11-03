# Metadatos y decisiones del feed web

`core/scraper.py:extraer_contexto_video` devuelve autor, descripcion y
sonido_original. Cada campo tiene su propio manejo de errores y límite de
longitud. En el orquestador se usa el contenedor activo, nunca todo el feed.
Los selectores son candidatos: deben validarse en el DOM de la sesión real.
No se afirma que estos selectores hayan sido verificados contra TikTok vivo.
Los archivos config/web_selectors.mobile.json y web_selectors.example.json
admiten un objeto metadata con selectores locales al contenedor activo.

`core/ai_agent.py:evaluar_con_openai` usa gpt-4o-mini con JSON Schema estricto
y valida los tipos, campos, coherencia de comentarios y longitud de hasta 8
palabras en minúsculas. La instrucción solicita máximo un emoji; la validación
local no cuenta grafemas emoji. Metadatos sin descripción no generan una
consulta: se devuelven recomendaciones false. Rechazos, respuestas truncadas,
errores y JSON inválido no habilitan acciones. El contexto del DOM va en el
mensaje user; las reglas permanecen en system. No se analiza imagen ni sonido.

El flujo Android conserva su esquema anterior. En web, comentario se adapta
internamente a texto_comentario para los ejecutores existentes. compartir
solo se registra; no hay ejecutor de compartidos. La evidencia post_decision
se captura antes de habilitar acciones; se revalidan contexto e identidad
del video. Sin --execute se conserva el modo sin interacciones sociales.

## Histórico local

Cada cuenta y ejecución escribe:

`logs/<account_id>/decisiones-<run_id>.jsonl`

Cada línea incluye schema_version, timestamp UTC, account_id, run_id,
cycle_id y evento. Los eventos context y decision conservan metadatos,
recomendación JSON, modelo, versión del prompt, latencia y disponibilidad de
evidencia. ai_error conserva tipo de error, no textos de excepciones con
posibles secretos. Los eventos de clic/envío no prueban aceptación del servidor.
Los registros se escriben y sincronizan a disco antes de continuar; un fallo
de persistencia no permite proseguir con acciones sin auditoría. No es una
cadena criptográfica de custodia ni una transacción con TikTok.

No se incluyen claves API, contraseñas, cookies ni configuración del proxy.
El texto público del video, autor y comentario sí quedan en el histórico local;
logs/ está excluido de Git. El operador controla su retención y acceso.
El esquema de selección y reservas del pool no se modifica; los endpoints
rotativos siguen requiriendo una configuración de salida acorde al supervisor.

## Resumen

Desde C:\Users\labor\OneDrive\Documents\ChatGPT\Framwork:

```powershell
Get-ChildItem .\logs -Recurse -Filter 'decisiones-*.jsonl'
.\.venv\Scripts\python.exe scripts/resumir_decisiones.py RUTA_ABSOLUTA_DEL_HISTORICO
```

El resumen cuenta recomendaciones de likes, comentarios y compartidos,
comentarios idénticos repetidos, errores IA, líneas inválidas y latencia media.
No asigna una puntuación de autenticidad ni certifica entrenamiento de cuenta.
Las pruebas usan respuestas simuladas; no hubo una ejecución de feed real ni
una consulta de pago a OpenAI durante esta integración.

Formato de salida verificado con OpenAI Docs:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat

Ruta async opcional y contratos: ver ASYNC_FEED.md.
