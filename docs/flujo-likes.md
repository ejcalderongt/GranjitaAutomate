# Primer flujo básico de Me gusta · v2.7

Fecha: 2026-10-24, America/Guatemala.

Ámbito: primera tarjeta de gt.granjita.lab, aplicación propia sin INTERNET. No usa redes sociales, URLs o cuentas reales. Receta recipes/lab-like.json, acción tipada lab_like, objetivo dejar marcado lab_like_01. No escribe comentarios ni hace scroll. Reutiliza Appium/UiAutomator2 y valida serial físico y paquete en primer plano antes de actuar.

Flujo: seleccionar placas → iniciar sesión de laboratorio → leer botón → pulsar solo si está en NO → verificar SI → guardar evidencia y resultado. Si ya estaba SI no vuelve a pulsar. Estado inesperado o falta de confirmación deja Revisar resultado; sin reintentos automáticos. Una repetición no se cuenta como un nuevo like real: el detalle informa si ya estaba marcado.

Desde Laboratorio Appium / Automate, pulsar Flujo básico: solo Me gusta, marcar una placa y Ejecutar prueba local. El comentario se deshabilita. El lote es secuencial; pausa entre placas y cancelación antes de la acción. Se exige piloto completado antes de lotes múltiples. Después puede seleccionarse un lote de placas elegibles. No se disparó un lote sobre toda la granja durante esta entrega.

SQLite automation.sqlite3 conserva acción lab_like, identidad, lote, estado, detalle y copia inmutable de receta/perfil con SHA-256. Las capturas se guardan localmente en data/lab-evidence; no se suben a GitHub. Los snapshots 4.2 pueden registrar referencias a estas tareas en la próxima captura, pero no respaldan las preferencias internas del laboratorio ni reejecutan likes al restaurar.

```powershell
# Validar receta
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/lab-like.json
# Ejecutar sobre una identidad explícita; repetir --device-id para un lote
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/lab-like.json --execute --device-id UUID_INTERNO
```

Validación automatizada: 53 pruebas con salida 0, incluyendo aplicación desde NO, conservación del SI sin volver a pulsar y receta local sin comentario. La app Android conserva el estado mediante sus preferencias normales; no se borraron datos para fabricar una transición NO→SI.

Piloto real completado con la receta lab-like-v1 en una placa elegible; tarea d48d9212-1809-45d1-8f40-3fd8775676d2 registrada en SQLite y evidencia local.
