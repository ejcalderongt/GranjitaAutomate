# Rescate de AGX

Verificado el **2026-10-28, America/Guatemala**. Fuente local: proyecto hermano
`AGX/data`. Se leyó mediante conexiones SQLite de solo lectura; no se ejecutaron
módulos de AGX ni se alteraron sus filas.

## Datos conservados

- 34 identidades físicas canónicas incorporadas al inventario, con alias históricos.
- 38 fichas de identidad y 4 relaciones de alias conservadas para trazabilidad.
- 10.798 filas históricas de `granjita.sqlite3` y `automation.sqlite3`, incluidas
  conexiones, snapshots lógicos, observaciones, tareas, recetas y verificaciones.
- Copia consistente de `traces.sqlite3`: 43.247 eventos y un feedback.
- 25 declaraciones manuales TikTok: 19 con cuenta declarada y 6 sin cuenta.
  Las declaraciones no son autenticación actual. Se conservan fecha y procedencia.

El inventario rescatado empieza desconectado y sin cuenta verificada. La
importación conserva estado, proxy y alias actuales si el dispositivo ya existe.
Las conexiones IP:puerto antiguas quedan como historia y no se convierten en
identidad permanente ni se ejecuta `adb connect` automáticamente.

## Almacenamiento y recuperación

La base operativa es `data/granja_tiktok.db`. Tablas nuevas:

- `legacy_agx_records`: evidencia original serializada, fuente y hash por fila.
- `legacy_agx_identities`: identidad anterior, canónica, serial físico y alias.

Las copias fuente, el respaldo previo del framework y el manifiesto con hashes
están en `data/imports/agx/<ejecución>/`. Son datos privados excluidos de Git.
Cada base se respalda de forma consistente mediante SQLite Backup; las tres
copias no representan una transacción común entre bases independientes.
Se conservó la historia de laboratorio separada de las métricas de TikTok.

La sección **Datos rescatados de AGX · históricos** del dashboard muestra
declaraciones, pantallas y paquetes observados con su fecha.

Repetir el rescate no duplica filas idénticas. Si una fila cambia en AGX, se
conservan ambas evidencias; no se elimina la versión anterior.

```powershell
.\.venv\Scripts\python.exe -m core.legacy_import --source ..\AGX
.\.venv\Scripts\python.exe -m core.legacy_import --source ..\AGX --apply
```

El primer comando inspecciona; el segundo respalda e importa. `--database RUTA`
permite elegir una base de destino fuera de AGX.

## Dependencias y diferencias detectadas

Se verificó `adb version` en los binarios de AGX y Panda: ambos indican
ADB 1.0.41 / Platform-Tools 34.0.1. La configuración local privada
`config/native_dependencies.local.json` apunta al SDK de AGX. `ADB_PATH`
explícito tiene prioridad; si no hay configuración se conserva el valor por
defecto `C:\Android\platform-tools\adb.exe`. No se arrancaron ni reiniciaron
servidores ADB para verificar los binarios.

Las 33 observaciones técnicas históricas de TikTok indican
`com.zhiliaoapp.musically`. Tras el ajuste solicitado por el operador, este es
el paquete por defecto en `config/tiktok_app.json`. El componente es
`com.zhiliaoapp.musically/com.ss.android.ugc.aweme.main.MainActivity`;
el histórico confirma el paquete, y la clase se valida en cada dispositivo
mediante resolución de Android antes de instalar proxy/firewall o abrir la app.
Se aceptan clases y componentes completos en `--activity`, con comprobación
del paquete APK. El namespace de la clase no determina el nombre del paquete.

Los workers del smoke toman alias y UUID canónico de `legacy_agx_identities`
por serial físico exacto. Ambos aparecen en logs y manifiesto. Las interacciones
nuevas conservan su clave `id_adb` e incluyen `legacy_device_id` para enlazar
la historia rescatada. No se crea otro dispositivo a partir del alias, ni se
atribuyen identidades por coincidencia de IP antigua.

Al comprobar los alias se encontró que los 38 campos de nombre de la BD original
estaban vacíos. Se recuperaron 33 nombres reales de `data/panda-inventory.json`
(evidencia del 2026-10-24), usando su `onlySerial` exacto. Se conserva el JSON
fuente junto a los snapshots, su hash y las filas históricas. La identidad sin
nombre conserva su serial; no se genera un alias ficticio. Reimportar mantiene
los nombres ya rescatados y los alias actuales del framework.

Comprobación física de solo lectura del 2026-10-28: ambos servidores respondieron
y expusieron 34 rutas autorizadas. En las tres primeras rutas se resolvió el
componente global anterior sin abrir TikTok. Todas las rutas autorizadas tenían
serial de transporte TCP: ninguna pasó el filtro USB directo del smoke existente.
El operador autorizó después el transporte TCP con verificación física. La
restricción de USB directo ya está retirada para las rutas Panda verificadas.
Nueva comprobación del 2026-10-28: **34 placas TCP enlazadas con AGX, cero nuevas,
cero incidencias de identidad**. Las tres primeras identidades seleccionadas
para el smoke tienen alias histórico; el componente global fue resuelto.

Se guardaron 34 direcciones observadas en `config/adb_devices.local.json`,
excluido de Git. El descubrimiento de granja puede reconectar esas direcciones
en su servidor original antes de volver a leer y verificar la identidad. Una
IP histórica nunca basta para atribuir el equipo: el JOIN se hace por serial
leído en ese momento. Los seriales físicos nuevos válidos se registran como
nuevos y sin cuenta verificada.
No se recuperaron proxies residenciales verificados; la plantilla de red sigue
pendiente de completar con datos reales.
