# Métricas y auditoría del flujo de likes · v2.8

Fecha: 2026-10-24, America/Guatemala. Ámbito: acción lab_like de Granjita Lab. No incluye publicaciones externas ni considera los likes del antiguo flujo combinado lab_smoke.

## Indicadores

| Indicador | Definición |
| --- | --- |
| Programados | Tareas lab_like registradas, incluyendo pendientes, canceladas e históricas. |
| Procesados | Tareas con evento started; se comenzó un intento, incluso si falla la sesión. |
| Aplicados | Tareas con resultado NO→SI verificado después de solicitar el clic. |
| Ya marcados | Tareas verificadas que ya estaban en SI; no se vuelve a pulsar. |
| Sin confirmar | Intentos iniciados sin evento de resultado verificado. No se infieren éxitos. |
| Históricos sin medición | Tareas anteriores sin contexto/eventos estructurados; no se recalculan likes por interpretar su texto. |

Los contadores agregan todo el historial lab_like de SQLite, no solo las últimas 300 filas visibles. Se cuenta cada tarea una vez, aunque tenga varios eventos. Aplicados cuenta transiciones verificadas por ejecución, no usuarios/publicaciones únicas ni la cardinalidad actual del feed. En el destino local de esta versión, repetir un like ya existente aumenta Procesados y Ya marcados, no Aplicados. Cancelar antes de iniciar no aumenta Procesados.

## Evidencia SQLite

En automation.sqlite3, like_context conserva una copia del UUID/serial físico, nombre, rack/posición disponibles, puerto y transporte ADB, ambiente, paquete y target exacto. like_events agrega eventos fechados: started, observed, click_requested, verified, evidence y cambios de estado de tarea. La receta completa y perfil con SHA-256 siguen en task_recipes. La exportación incluye ese contenido además de los eventos y los indicadores.

El evento click_requested se persiste antes de pulsar. verified se persiste inmediatamente después de verificar SI, antes de capturar pantalla. Si luego falla la captura, el like verificado conserva su clasificación y la tarea puede quedar para revisión por falta de evidencia. Captura de pantalla local con ruta y SHA-256 cuando está disponible. Una caída entre clic y verificación deja resultado sin confirmar; no hay reintento automático ni conteo como Aplicado.

Antes de agregar las tablas se respalda una base existente sin métricas en automation-antes-metricas.sqlite3. Los eventos se agregan, sin una operación de edición desde el programa. SQLite y hashes locales ayudan a revisar consistencia, pero no son una firma, un sello externo ni un registro resistente a alteración deliberada del archivo. Mantener copias externas si se necesita preservar evidencia fuera del equipo.

## Interfaz y exportación

El panel Laboratorio Appium / Automate muestra los indicadores y el botón Exportar auditoría de likes (JSON). Seleccionar una tarea lab_like muestra destino, resultado, hash de receta y eventos. La exportación se guarda en una ruta elegida por el usuario, con metadatos privados de dispositivos: no subirla al repositorio público.

El destino actual es el paquete gt.granjita.lab, elemento lab_like_01. No se almacena una URL porque no existe una publicación web en este flujo. El mapa físico puede estar vacío hasta completar la asignación; no se inventan valores. El texto histórico no se convierte en una medición nueva.

## Validación

56 pruebas pasan con salida 0. Se verifican conteo por tarea sin duplicar eventos, diferencia entre aplicado/ya marcado/sin confirmar, cancelación sin iniciar y preservación de históricos. Prueba real de la receta con auditoría estructurada documentada en bitácora.


Actualización v2.9: el nuevo lab_like_flow se incluye en los indicadores. Cada tarjeta destino de una tarea es una interacción distinta; se deduplica por tarea y target. Programados cuenta tareas, mientras los demás contadores cuentan interacciones. Ver docs/creador-tareas.md.
