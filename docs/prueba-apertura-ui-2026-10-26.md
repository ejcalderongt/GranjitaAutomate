# Prueba de apertura desde la aplicación · 2026-10-26

Fecha y zona: America/Guatemala. Se ejecutó y comprobó mediante los controles reales de Automatización 2.19, a solicitud del usuario.

## Selección y ejecución

Se identificaron las 14 fichas Cancelado del lote anterior 48dfacb8-0648-4599-a01a-277fa5f1f795. Se inició GranjitaAutomate con iniciar.vbs y terminó su verificación de 29 snapshots sin errores. Desde Automatización se eligió TikTok, se desmarcó la selección y se marcaron únicamente esas 14 fichas. Se pulsó Abrir y comprobar app; la aplicación ejecutó su preflight, apertura secuencial y verificación posterior sin invocar el ejecutor por CLI.

El controlador de ventanas no manejó de forma estable el diálogo dependiente de la ventana principal (índice no disponible y geometría no disponible). Se abrió el mismo AutomationDialog como ventana independiente y se usaron sus botones y casillas mediante computer-use. No se parchearon callbacks, trabajadores, selección ni resultados. La prueba de ejecución y de cierre se leyó en esa ventana real.

El panel de Automatización mostró 2.19. Se detectó un rótulo histórico fijo 2.13 en la ventana principal; no debe usarse como prueba de versión del código cargado. Corregir ese rótulo queda pendiente.

## Resultado confirmado

Nuevo lote dbe48acd-aaab-4836-bf41-1b45691b4ffd, creado 20:03:14 GT, comprobación posterior finalizada 20:03:59 GT:

- 14 tareas completadas y cero canceladas o para revisar.
- 13 lanzamientos; una app ya abierta, conservada sin relanzar.
- Verificación posterior: 14 en primer plano.
- La interfaz mostró Lote terminado, 14/14 Apps verificadas, cero Para revisar y cero Sin ejecutar, con fondo verde.
- Consulta secundaria de SQLite: la selección coincide exactamente con las 14 fichas pendientes y las 14 comprobaciones están guardadas.
- Cero eventos de error de trazas ligados a los task_id del nuevo lote. No se borraron logs después de la prueba.

No se ejecutaron likes, no se completaron bienvenidas, no se eligieron datos de perfil ni se iniciaron sesiones. Confirmar primer plano no demuestra cuenta preparada ni publicación visible. La ventana validada se dejó abierta en Resultados y auditoría.

## Reproducir

Abrir desde el acceso directo, Automatización → Tarea → App origen TikTok; seleccionar las fichas elegidas; Abrir y comprobar app; esperar Lote terminado y Verificación terminada. Los seriales y UUID por dispositivo permanecen exclusivamente en SQLite/data y no se incluyen en Git.

En caso de que el controlador no pueda actuar sobre el diálogo dependiente, el mismo panel se puede mostrar como ventana principal de Qt (sin ejecutar acciones mediante código):

```python
from PySide6.QtWidgets import QApplication
from granjita.inventory import FleetStore
from granjita.automation_ui import AutomationDialog
app = QApplication([])
app.setStyle('Fusion')
dialog = AutomationDialog(FleetStore())
dialog.show()
app.exec()
```

Ejecutar solo cuando no haya tareas activas; JobStore recupera tareas incompletas al abrir. Las acciones y selección siguen realizándose en la UI. El lanzador temporal y los identificadores usados quedaron en data/, excluidos de Git; el ejemplo anterior permite reproducir la apertura del panel sin depender de esos archivos privados.
