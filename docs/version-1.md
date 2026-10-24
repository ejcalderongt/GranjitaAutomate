# GranjitaAutomate v1.0

Aplicación de escritorio Windows con Python, PySide6 y SQLite. Conexión principal: OTG mediante el proceso de Panda.

## Abrir

Usar el acceso directo **GranjitaAutomate** del escritorio. También se puede ejecutar `iniciar.vbs` en la carpeta del proyecto.

1. Abrir Panda y completar el proceso OTG habitual.
2. Abrir GranjitaAutomate. La búsqueda inicial es automática.
3. Revisar los estados; **Validado** requiere una respuesta real de la placa.
4. Seleccionar una placa para ver el diagnóstico. Doble clic para asignar un nombre.
5. Si hay un problema, seguir la indicación y pulsar **Buscar y validar / Reintentar**.

La revisión cada 30 segundos es opcional. El programa no necesita que la ventana de Panda esté en primer plano, pero sí que el proceso de Panda haya expuesto las placas al servidor ADB local.

## SQLite portable

La base está en `data/granjita.sqlite3`, junto al programa. Guarda inventario, alias, resultados de validación, historial y configuración. No requiere instalar un servidor. Se excluye de Git porque contiene identificadores de dispositivos.

Usar **Respaldar SQLite** para crear una copia consistente en la ubicación elegida. Para restaurar, cerrar el programa y reemplazar `data/granjita.sqlite3` por la copia. No abrir simultáneamente la misma base desde varias computadoras ni sincronizarla mientras está en uso. La portabilidad de la base no implica que el entorno Python sea portable.

## Alcance y compatibilidad

- Consulta directamente el protocolo del servidor ADB en `127.0.0.1:5037`; el puerto puede cambiarse en Configuración.
- No ejecuta otro cliente ADB para detectar o validar: evita reinicios por diferencias de versión.
- Hasta cuatro consultas simultáneas con tiempo límite por dispositivo.
- Cuando falla la consulta al servidor, la interfaz indica que los datos guardados no son el estado actual.
- Detecta equipos expuestos por ADB; no puede certificar por sí sola que cada transporte sea OTG. El flujo OTG se establece en Panda.
- La columna **Acceso ADB** distingue identificadores TCP/IP de USB/otros. En la prueba real los 17 accesos eran TCP/IP: falta validar con el usuario el proceso OTG deseado en Panda.
- No pulsa botones de Panda ni configura físicamente el USB. La recuperación en v1 es guiada y el reintento valida de nuevo.
- La visualización de pantallas se realiza desde Panda en esta versión. La integración opcional con scrcpy queda pendiente.
- Requiere permisos suficientes para acceder al servidor ADB de Panda.

## Instalación en otra carpeta o equipo

Instalar Python compatible con PySide6 (esta versión se probó con Python 3.12.14), después:

```powershell
.\scripts\install.ps1 -Python 'C:\ruta\python.exe'
```

Esto crea `.venv`, instala las dependencias fijadas y genera el acceso directo. Si se mueve la carpeta, recrear el entorno y ejecutar `scripts/shortcut.ps1`. Panda se instala y configura por separado.

## Validación de desarrollo

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m granjita
```

Prueba real del 2026-10-23: 17 dispositivos expuestos por el servidor local respondieron correctamente; reportaron Android 12. No equivale al inventario total de la granja ni confirma la recuperación automática de fallos físicos.
