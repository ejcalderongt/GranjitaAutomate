# Comparación Panda y Granjita · 2026-10-26

Validación de lectura a las 18:39 GT, sin reconexiones, reinicios, tareas ni modificación de identidades.

## Hechos actuales

- Captura del usuario: 39 registros, 33 conectados y seis desconectados (01, 18, 19, 20, 21, 45).
- API local Panda: 33 conexiones, con 33 seriales físicos distintos.
- Búsqueda con scan_fleet: 16 conexiones en 5037 y 18 en 5038; las 34 respondieron.
- Son 33 transportes únicos y 33 seriales físicos únicos. El número Panda 46 aparece en ambos servidores.
- Coinciden los 33 transportes y los 33 seriales físicos entre API y búsqueda. Cero dispositivos exclusivos de uno u otro conjunto activo.
- La base del programa, comprobada por última vez a las 18:33:58 GT, conserva 27 conexiones validadas y siete en conflicto de identidad. Estas siete corresponden a seis equipos físicos actuales: números Panda 06, 30, 46, 50, 51 y 65.

## Interpretación

La detección ADB alcanza los mismos 33 equipos que Panda. El indicador principal cuenta seriales de conexiones con estado Validado; excluye los conflictos históricos, por lo que puede mostrar 27. No es una pérdida de seis conexiones: el programa bloquea su asociación con fichas cuyo serial anterior difiere del actual. No se fusionaron ni reasignaron fichas en esta revisión.

El número total de registros guardados en Panda (39) tampoco equivale al número de equipos conectados (33). Su API list consultada devuelve los activos y no permite confirmar por sí sola las seis fichas desconectadas; esa evidencia procede de la captura.

## Logs

Consulta operativa del día: 69 eventos de error, 68 timeouts de adb.reconnect (66 en 5037 y dos en 5038) y un timeout de panda.list. Son eventos/intentos, no dispositivos únicos fallidos. La consulta actual de Panda y ambos servidores respondió correctamente.

El resumen general de scripts.diagnostics alcanzó el límite de 10 000 eventos; no representa todo el historial. Las duraciones históricas más altas incluyen snapshots de aproximadamente 60 segundos, sin demostrar una falla actual.

## Pendientes y mejoras propuestas

1. Separar en el panel detectados físicamente (33 en esta muestra), asociados/aptos y conflictos; conservar el bloqueo de ejecución de identidades ambiguas.
2. Revisar los seis cambios de identidad con serial actual, ficha anterior y confirmación física; conservar historial antes de reasignar.
3. Identificar y evitar reintentos repetidos sobre direcciones históricas que ya no corresponden, sin asumir que un timeout es una avería eléctrica.
4. Mantener el deduplicado físico: dos servidores pueden listar el mismo equipo.

## Reproducción y evidencia

Consulta mediante granjita.panda_api.list_devices y granjita.inventory.scan_fleet([5037,5038]); comparar conjuntos serial y onlySerial contra serial y hardware_serial, respectivamente. Usar sqlite3 en modo read-only para consultar conexiones y trace_events, sin crear JobStore.

La respuesta completa quedó únicamente en data/comparison-current.json (privada, excluida de Git). Este documento contiene cantidades y números de pantalla, sin nombres de cuentas, IP ni seriales privados. No se cambió código ni se requiere incrementar versión por esta revisión.
