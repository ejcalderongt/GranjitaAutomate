# Contexto de la granja

Este archivo conserva el contexto original del 2026-10-23. Para el estado consolidado posterior y la continuidad de nuevas conversaciones, leer [Contexto inicial](contexto-inicial.md); las limitaciones iniciales que siguen no describen por sí solas la versión actual.

## Contexto recuperado el 2026-10-23

Fuente: historial de los chats «Consultar paquete VIP de Panda» y «Automatizar Granja Con ADB». Son referencias históricas; el estado actual requiere verificación.

- El usuario administra una granja de placas Android con Panda.
- El usuario indicó que pagó el paquete VIP. Una respuesta anterior describió una compra por 365 días y un botón pendiente de activación. No se verificó la activación final en este trabajo.
- Una respuesta anterior identificó Panda v9.12.213 y describió 31 de 41 dispositivos conectados en una captura. No representa un inventario actual.
- El usuario consultó sobre ADB para realizar desplazamientos, likes y comentarios. No hay implementación ni prueba confirmada en los chats revisados.

## Decisión de organización

El 2026-10-23 el usuario solicitó respaldar y organizar el conocimiento y lo que se cree en https://github.com/ejcalderongt/GranjitaAutomate.

## Decisiones confirmadas el 2026-10-23

- El usuario aprobó Python + PySide6, ADB, scrcpy opcional y SQLite como arquitectura propuesta.
- La intención es mantener las placas conectadas vía OTG mediante el proceso de Panda.
- La compatibilidad concreta entre ese proceso y el acceso ADB de nuestra aplicación todavía requiere inspección.
- El usuario autorizó construir v1, dejar acceso directo y utilizar SQLite portable.

## Inspección del 2026-10-23

- Se encontró ADB 34.0.1 incluido en la instalación de Panda y un servidor escuchando localmente en el puerto 5037. No se pudo atribuir con certeza el proceso del servidor a un ejecutable mediante la inspección disponible.
- Mediante el protocolo del servidor se detectaron y validaron 17 dispositivos que reportaron Android 12. No se verificó físicamente el tipo de transporte de cada placa.
- Los identificadores observados fueron direcciones TCP/IP. Esto confirma el acceso ADB por red expuesto actualmente, no que el flujo físico OTG solicitado ya esté configurado. Se distingue en la interfaz.

## Datos técnicos por confirmar

- Inventario actual de placas, modelos, versiones Android y conectividad.
- Estado de activación y funciones disponibles en Panda VIP.
- Herramientas existentes, configuración ADB y trabajo previo fuera de este repositorio.
- Objetivos concretos y criterios de aceptación de las próximas herramientas.
