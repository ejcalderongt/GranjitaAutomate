# Revisión del lote y presentación de resultados · v2.15

Fecha: 2026-10-26, America/Guatemala. Lectura de SQLite y trazas sin crear JobStore ni ejecutar tareas nuevas.

## Último lote enviado

Lote 340315f6-f045-4584-92b7-13000311d49f, creado 19:24:08 GT y terminado 19:24:12. Contiene una sola tarea app_prepare, perfil origen TikTok. Estado guardado Completado; resultado foreground_verified=true, launched=true, like_mapping=pending, interaction_ready=false, readiness_reason=mapping_pending.

La traza app.source.prepare terminó ok en 4111.7 ms. No hay eventos de error vinculados a esta tarea. No se envió una acción de likes ni hubo fallo técnico de apertura. El lote contenía un dispositivo, aunque el selector de cantidad pueda indicar diez: lo que determina el envío son las casillas realmente seleccionadas y la selección congelada antes de validar conexiones.

El bloqueo de likes es el mapeo pendiente; abrir TikTok no valida publicación, estado del botón ni sesión. La captura previa muestra bienvenida en pantalla 06, pero este lote corresponde a otra ficha: no se debe atribuir aquella captura a este dispositivo sin comprobarlo.

## Último lote múltiple de likes (histórico)

Lote 53bd433d-1d3b-442a-99f6-237d38dba62e, del 2026-10-24 a las 19:38 GT, laboratorio local, 28 dispositivos:

- Una tarea completada: tres tarjetas ya marcadas.
- Una tarea para revisar: detenida por la condición de cancelación antes de la siguiente acción, después de verificar dos tarjetas ya marcadas.
- 26 tareas canceladas antes de iniciar.
- 84 tarjetas planificadas; cinco verificadas, todas ya marcadas; 79 sin iniciar; cero clics solicitados sin verificación y cero likes nuevos.

La evidencia muestra cancelación, no un fallo de Appium en este lote. No identifica quién originó la cancelación. Las tareas y métricas históricas se conservan intactas.

## Corrección visible

El rótulo Completado era ambiguo para app_prepare. Ahora Resultados y auditoría muestra:

- Resumen del último lote, fecha/hora, dispositivos realmente enviados, app/acción, apps abiertas y mapeos pendientes.
- Columna App / acción y resultado App abierta · Likes pendientes de mapeo cuando así lo acredita el JSON guardado.
- Likes históricos separados del resumen del lote: no se atribuyen los 78 likes anteriores a la apertura actual.
- Canceladas separadas de los resultados para revisar; no se cuentan como fallos técnicos.

Solo cambia presentación, no estados persistidos ni interpretación de interacciones. Un resultado antiguo sin foreground_verified no se presenta como app abierta verificada. El resumen consulta el lote completo aunque el historial visible tenga límite de 300 filas.

## Reproducción y validación

```powershell
.\.venv\Scripts\python.exe -m scripts.review_results --batch-id 53bd433d-1d3b-442a-99f6-237d38dba62e --output data/review-last-like-batch.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

El resumen global de trazas se limita a 10 000 eventos y puede no incluir errores históricos; el diagnóstico del último lote usa consulta directa por task_id. Los detalles de tareas y eventos de likes se consultan completos por batch.

91 pruebas correctas y revisión visual del panel sobre datos actuales en modo de lectura. No se relanzaron lotes ni se pulsaron likes. Los datos privados y la captura del panel quedan fuera de Git.
