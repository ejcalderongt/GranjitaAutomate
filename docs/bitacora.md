# Bitácora

## 2026-10-23

- Se recuperó el contexto disponible de los chats sobre Panda VIP y ADB.
- Se vinculó la carpeta de trabajo AGX con el repositorio GranjitaAutomate.
- Se creó la estructura inicial de documentación y las instrucciones de mantenimiento.
- No se ejecutaron cambios sobre las placas Android.
- Se documentó una propuesta inicial de asistente de conexión con Python, PySide6, ADB y scrcpy opcional. Falta confirmar conexión física y versiones Android; la tecnología aún no fue aprobada por el usuario.
- Posteriormente el usuario aprobó la arquitectura y confirmó OTG mediante el proceso de Panda como conexión permanente deseada. Se actualizó la propuesta; queda pendiente verificar la integración técnica con Panda.
- Se construyó v1 con PySide6 y SQLite portable: detección y validación asíncronas, inventario, alias, historial, reintentos guiados, revisión periódica opcional, apertura de Panda y respaldo SQLite.
- Se confirmó comunicación real con 17 dispositivos Android 12 mediante el servidor ADB local, sin reiniciarlo. Se evita ejecutar un cliente ADB de otra versión.
- Los accesos observados son TCP/IP, por lo que la conexión física OTG no se da por validada. Se añadió la distinción a la interfaz.
- Se creó el acceso directo del escritorio y se verificó la interfaz con las 17 placas. Pasaron cinco pruebas de protocolo, autorización, tiempo límite, inventario, persistencia de alias y respaldo SQLite.
- Se diagnosticó la diferencia Panda 41 / aplicación 17: existen dos servidores ADB, con 17 y 16 dispositivos distintos respectivamente, en 5037 y 5038. Se validaron los 16 del segundo servidor. Falta soporte de inventario combinado y reconciliar los registros desconectados de Panda. Se guardó un diagnóstico reproducible sin identificadores privados.
- Se confirmó por los procesos padre que Panda (touping) inició ambos procesos adb a la misma hora. El motivo interno del reparto sigue sin confirmarse; gestión por grupos o carga es solamente una hipótesis.
- El usuario definió fase 2 (inventario detallado) y fase 3 (tareas e interpretación contextual mediante IA en cuentas controladas). Se registró la hoja de ruta y la propuesta de evaluar ADB/Automate antes de un agente Android propio. No se instalaron agentes ni se ejecutaron interacciones en cuentas.
- Se implementó v2: panel de servidores/puertos/PID, agregación de conexiones, búsqueda, fichas de inventario con 34 observaciones, evidencia y cambios, asociación física explícita y manejo de fallos parciales.
- Se migró SQLite con respaldo previo y conservación de alias/eventos. Se inventariaron 33 conexiones. En 14 se observó su y en 19 no, sin ejecutar su ni confirmar ausencia de root.
- Pasaron once pruebas automatizadas y se revisaron visualmente la ventana y la ficha de inventario.

## 2026-10-24

- Se implementó v2.1 con nombres automáticos basados en serial físico, columna separada de identidad, conservación de alias y asociación conservadora después de cambios de IP.
- Se agregó respaldo previo a migración SQLite v3, recuperación de seriales de capturas existentes y alertas por seriales repetidos o cambios de identidad en una IP.
- Pasaron 15 pruebas y se verificó la interfaz con datos reales. Se observaron un serial compartido entre dos fichas y una conexión con identidad en conflicto; no se fusionaron ni sobrescribieron automáticamente.
- Se incorporó a AGENTS.md la instrucción de hacer commit y push después de cada avance funcional verificado.
- Se documentó una propuesta de gestión social con cuentas separadas de placas, grupos, trabajos persistentes, estadísticas verificables, adaptadores API y ejecución Android de laboratorio. Se recomienda Appium/UiAutomator2 para el piloto y evaluar Automate para flujos sencillos. No se instalaron herramientas ni se ejecutaron acciones sociales.
