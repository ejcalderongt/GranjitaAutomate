# App origen · v2.14

Fecha: 2026-10-26, America/Guatemala.

## Uso

Automatización → Tarea → Receta → App origen: Granjita Lab o TikTok.

Seleccionar dispositivos y pulsar Abrir y comprobar app. La comprobación actual de conexiones precede al lote. Cada placa valida su serial, busca el paquete instalado, resuelve la actividad launcher si hace falta abrirla y verifica primer plano. Si ya está abierta, no la reinicia. Si falta o hay varias variantes compatibles, el resultado requiere revisión; no instala apps ni elige silenciosamente entre variantes.

Abrir y comprobar es una operación inmediata independiente del horario de likes. No hace scroll ni pulsa botones de bienvenida, permisos, login o likes. Cada tarea queda en SQLite con receta, perfil origen completo y SHA-256, estado y resultado JSON. Una preparación completada significa primer plano verificado, no una cuenta lista ni una interacción realizada. No habilita por sí sola el piloto requerido para un lote de likes.

## Perfiles y recetas

El perfil de ejecución existente laboratorio conserva la configuración de herramientas. El nuevo campo app_source identifica la aplicación destino y se guarda aparte mediante _app_source_snapshot en task_recipes. Registro reproducible en granjita/app_sources.py; no son paquetes arbitrarios introducidos por texto.

- laboratorio: gt.granjita.lab, adaptador lab_like_v1 verificado. Su sesión Appium ya instala/actualiza la APK propia y abre la actividad antes de comprobar el paquete y procesar tarjetas.
- tiktok: com.zhiliaoapp.musically o com.ss.android.ugc.trill, apertura verificada; adaptador de likes pendiente. Tener dos variantes instaladas requiere un perfil específico.

Las recetas antiguas sin app_source conservan laboratorio. Los perfiles externos no heredan los selectores lab_like_XX. La UI bloquea la ejecución de likes sin adaptador verificado; también se comprueba en JobStore.create y execute_recipe para impedir que la CLI omita ese control. Abrir la app no modifica métricas de likes.

Ejemplo reproducible:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/tiktok-prepare.json
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/tiktok-prepare.json --execute --device-id UUID_ELEGIDO
```

La primera orden valida/previsualiza. La segunda abre/comprueba únicamente la ficha explícita. Las recetas de preparación usan action=app_prepare, context.environment=device_app y parameters={}. Se pueden cargar y guardar desde el panel.

## Pruebas y hechos observados

87 pruebas correctas, incluidas apertura cuando está cerrada, conservación de app abierta, ausencia de app, variantes ambiguas, cancelación, bloqueo de mapeo no validado, compatibilidad de recetas antiguas y persistencia desde GUI sin incrementar likes. Revisión visual del selector y controles deshabilitados para TikTok pendiente de mapeo.

Piloto real en pantalla Panda 06: tarea de apertura completada; después, una segunda tarea confirmó que seguía en primer plano sin relanzarla. Paquete com.zhiliaoapp.musically. Ambas persistidas en automation.sqlite3. No se pulsó ningún like. Las trazas de preparación incluyen task_id, perfil y paquete, sin cuerpo de pantalla ni datos de cuentas.

La captura aportada por el usuario muestra bienvenida de TikTok en 06. Es evidencia visual de una pantalla inicial, no de publicación visible ni sesión lista. El programa no detecta automáticamente esa bienvenida en esta versión: devuelve interaction_ready=false y mapping_pending para TikTok, aun cuando foreground_verified=true. No se aceptaron condiciones ni se completó login.

## Pendiente para likes TikTok

Preparar la bienvenida/sesión y una publicación de prueba identificable. Validar selector, estado sin like/con like y forma de identificar cada publicación antes de implementar el adaptador. Evitar coordenadas fijas y no repetir clics de resultado incierto. Hasta entonces, solo el laboratorio ejecuta likes; no se presenta esta entrega como un flujo completo de likes de TikTok.

Persistencia sin migración de esquema: tasks, task_recipes y resultados existentes. Bases y evidencias permanecen locales excluidas de Git; el repositorio respalda código, receta y documentación.
