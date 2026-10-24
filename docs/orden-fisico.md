# Orden permanente por rack y posición · v2.5

Fecha: 2026-10-24, America/Guatemala.

La vista principal usa orden físico: rack, posición y nombre. Activos primero es opcional y se recuerda en SQLite. Los desconectados conservan su posición; no se renumeran las otras placas. Se muestra una fila por ficha, escogiendo un transporte validado cuando existe, sin borrar conexiones históricas. Varias fichas con un mismo serial siguen separadas y requieren revisión; no se fusionan automáticamente.

## Asignar

1. Abrir la versión actual y conciliar.
2. Seleccionar una placa validada y pulsar Asignar rack / posición.
3. Introducir rack (R01, R02…), posición y número permanente Panda. El número Panda es global y debe ser único; por ejemplo R01 posición 20 podría usar 120 y R02 posición 20, 220. Es una convención propuesta, no una asignación ya aplicada.
4. Confirmar físicamente la correspondencia y pulsar Verificar serial y guardar posición. Se vuelve a consultar getprop en el transporte seleccionado antes de guardar.

La posición se asocia al serial físico y no a la IP. La base rechaza seriales sin ficha única, fuentes en conflicto, posiciones ocupadas y números duplicados. Un cambio legítimo de serial/ROM requiere revisión. La migración SQLite v4 crea physical_positions y respalda antes en granjita-antes-v4.sqlite3. Las asignaciones reales permanecen en data/, fuera de Git; se respaldan con Respaldar SQLite.

## Aplicar a Panda

El segundo botón del diálogo aplica el mapa ya guardado a una sola placa mediante updateDevices. Nombre R01-P20 y número elegido. Antes verifica de nuevo el serial por ADB, una única coincidencia onlySerial de Panda y el mismo transporte. Rechaza un número ocupado por otra placa; no desplaza ni renumera dispositivos ajenos para liberar ese número. Guarda evidencia anterior en data/panda-position-changes.jsonl y vuelve a consultar la API para confirmar el resultado. Un timeout o falta de confirmación requiere consulta y revisión antes de reintentar, sin reintentos automáticos.

La sincronización es explícita, no se ejecuta al arrancar ni desde texto libre. No cambia Android. El orden local sí está bajo nuestro control; la permanencia y criterio visual de orden de Panda tras reiniciarlo requieren prueba real. Fuente: https://doc.some3c.com/panda-manual/api-documentation (updateDevices).

## Estado inicial y validación

Las referencias tarjeta 10→pantalla 65, 17→30 y 20→51 están confirmadas por el usuario, pero faltan rack y seriales comprobados. No se transformaron esas referencias en posiciones persistentes por suposición. Todas las fichas sin asignación muestran Sin asignar, después de las asignadas. No se cambiaron nombres o números reales en Panda durante esta implementación, al no existir todavía mapa físico verificado.

41 pruebas pasan con salida 0. Incluyen posición conservada al desconectar, vista opcional activos primero, múltiples transportes por ficha, persistencia al reabrir SQLite, colisiones sin sobreescritura, respaldo de migración y sincronización Panda simulada con lectura posterior. Se revisó el panel renderizado con 37 fichas y 14 columnas; ese recuento es histórico, no una búsqueda actual de dispositivos.
