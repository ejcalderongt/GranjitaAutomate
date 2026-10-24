# Propuesta: asistente de conexión

Fecha: 2026-10-23. Estado: arquitectura aprobada; v1 implementada. Ver docs/version-1.md para alcance y limitaciones comprobadas.

## Decisión aprobada

Las placas deben permanecer conectadas vía OTG mediante el proceso de Panda. El asistente acompañará ese flujo, detectará los dispositivos y validará su disponibilidad. Falta inspeccionar cómo Panda expone esas conexiones a ADB; no se presupone una API ni acceso ADB compatible hasta verificarlo.

## Objetivo

Programa de escritorio para Windows, amigable y semiautomático, que detecte dispositivos Android, valide comunicación y guíe las intervenciones necesarias.

## Base recomendada

- Python + PySide6 para la interfaz y el asistente por pasos.
- Android SDK Platform Tools (ADB) para detectar y comunicarse con las placas.
- scrcpy como opción para abrir la pantalla de un dispositivo autorizado.
- SQLite para inventario e historial local, excluido del repositorio si contiene datos privados.

## Flujo propuesto

1. Revisar instalación y versión de ADB, considerando la instalación que usa Panda.
2. Detectar las placas conectadas vía OTG mediante Panda, una vez verificado el acceso compatible a ADB.
3. Mostrar estados: detectado, pendiente de autorización, sin respuesta y validado.
4. Validar cada equipo con una consulta real y tiempo límite; aparecer en la lista de ADB no basta.
5. Guiar al usuario para autorizar en Android, revisar cableado o completar el proceso de Panda cuando corresponda.
6. Permitir alias por placa, reintentos limitados y verificación posterior.
7. Mostrar resumen de conectados, pendientes y fallidos, con diagnóstico comprensible.

No reiniciar globalmente el servidor ADB como recuperación automática: puede afectar Panda y otros equipos. La autorización RSA y el emparejamiento pueden requerir intervención del usuario.

## Información pendiente

Inspeccionar el proceso OTG de Panda, ubicación y versión de su ADB, visibilidad de las placas y versiones Android antes de implementar la conexión. La conexión por red no es parte del flujo inicial solicitado.

## Referencias

- https://developer.android.com/tools/adb
- https://doc.qt.io/qtforpython-6/index.html
- https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html
- https://github.com/Genymobile/scrcpy
