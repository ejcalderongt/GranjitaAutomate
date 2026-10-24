# Propuesta: asistente de conexión

Fecha: 2026-10-23. Estado: recomendación pendiente de validación con el usuario; sin implementación.

## Objetivo

Programa de escritorio para Windows, amigable y semiautomático, que detecte dispositivos Android, valide comunicación y guíe las intervenciones necesarias.

## Base recomendada

- Python + PySide6 para la interfaz y el asistente por pasos.
- Android SDK Platform Tools (ADB) para detectar y comunicarse con las placas.
- scrcpy como opción para abrir la pantalla de un dispositivo autorizado.
- SQLite para inventario e historial local, excluido del repositorio si contiene datos privados.

## Flujo propuesto

1. Revisar instalación y versión de ADB, considerando la instalación que usa Panda.
2. Detectar equipos USB y permitir conexión a direcciones de red conocidas.
3. Mostrar estados: detectado, pendiente de autorización, sin respuesta y validado.
4. Validar cada equipo con una consulta real y tiempo límite; aparecer en la lista de ADB no basta.
5. Guiar al usuario para autorizar en Android, revisar cableado o emparejar cuando corresponda.
6. Permitir alias por placa, reintentos limitados y verificación posterior.
7. Mostrar resumen de conectados, pendientes y fallidos, con diagnóstico comprensible.

No reiniciar globalmente el servidor ADB como recuperación automática: puede afectar Panda y otros equipos. La autorización RSA y el emparejamiento pueden requerir intervención del usuario.

## Información pendiente

Confirmar si las placas se conectan por USB, red o ambas, versión Android y forma de conexión actual en Panda antes de implementar el asistente.

## Referencias

- https://developer.android.com/tools/adb
- https://doc.qt.io/qtforpython-6/index.html
- https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html
- https://github.com/Genymobile/scrcpy
