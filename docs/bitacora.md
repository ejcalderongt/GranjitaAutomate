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
