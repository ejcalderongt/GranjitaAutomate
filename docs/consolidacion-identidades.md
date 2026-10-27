# Consolidación de identidades · v2.20

Fecha: 2026-10-26, America/Guatemala. Aplicación explícita autorizada por el usuario para pantallas Panda 04, 11, 28 y 62.

## Hallazgo y criterio

Cada caso tenía dos fichas históricas con el mismo serial, fabricante y modelo. Una estaba activa; la otra tenía conexión ausente o ninguna conexión. Las cuatro tenían alias vacío y ningún checkpoint lógico asociado. No se asumió que fueran dispositivos diferentes por cambiar de servidor/IP.

La herramienta consulta Android y Panda, exige un único transporte actual por serial físico, fuentes de identidad concordantes y fabricante/modelo iguales. Verifica los servidores de todas las conexiones históricas. Si un serial está simultáneamente en transportes distintos, una conexión corresponde ahora a otro serial, faltan servidores, hay metadatos/alias incompatibles o referencias previas encadenadas, se detiene para revisión.

## Persistencia

Esquema principal SQLite 6, con respaldo previo granjita-antes-v6.sqlite3. Nueva tabla device_identity_aliases: alias_id, canonical_id, at y evidencia JSON. Se conserva como canónica la ficha de creación más antigua (UUID como desempate), y las restantes quedan como referencias históricas.

No se borran inventory_devices, device_identity, snapshots, observaciones, checkpoints, archivos ni tareas. Se redirigen conexiones a la ficha canónica y se registran eventos en todas las fichas. Los conteos y candidatos activos excluyen referencias históricas; historial e inventario consultan toda la familia. Los manifiestos de snapshots nuevos incluyen tareas de UUID canónico y referencias, sin reescribir manifiestos anteriores. Alias de nombre se conserva si existe uno inequívoco.

Las referencias anteriores se consultan por UUID y el cambio de nombre resuelve hacia la canónica. La asociación manual de conexiones protege fichas consolidadas de eliminación. El script anterior de reasignación reconoce la ficha activa sin tratar referencias históricas como candidatos duplicados.

## Reproducir

Cerrar ventanas antiguas y esperar a que terminen tareas. La CLI bloquea aplicación si hay trabajos activos. Vista previa y aplicación:

```powershell
.\.venv\Scripts\python.exe -m scripts.consolidar_identidades --panda-number 4 --panda-number 11 --panda-number 28 --panda-number 62
.\.venv\Scripts\python.exe -m scripts.consolidar_identidades --panda-number 4 --panda-number 11 --panda-number 28 --panda-number 62 --apply
```

Antes de aplicar crea un respaldo coherente adicional en data/backups; relee Android/Panda y revalida la base dentro de una transacción atómica. Auditoría preparada/confirmada en data/consolidacion-identidades-*.json y evidencia en SQLite. Estos archivos contienen identificadores y no se versionan.

Verificación real tras consolidar, 20:19:13 GT: 33 en línea, 33 aptos, cero filas con serial repetido e integrity_check=ok. Se conservaron exactamente 38 fichas, 38 registros de identidad, 35 snapshots de inventario, 1188 observaciones, 48 checkpoints y un archivo de checkpoint. Las cuatro referencias históricas ya no se cuentan como cuatro placas adicionales.

## Prueba UI

Panel real Automatización 2.20, Todos → TikTok → Abrir y comprobar app. Lote de85e30c-c095-4978-85aa-ceb360a0d57f, 20:22:50–20:23:23 GT: 33 completadas y 33 confirmadas en primer plano, cero errores de traza ligados al lote. Cuatro lanzamientos (04, 11, 28, 62) y 29 apps ya abiertas. Se observó el indicador verde 33/33 en la app; la selección, ejecución y segunda comprobación siguieron el flujo normal de UI.

No se ejecutaron likes ni se completaron bienvenidas, perfiles o login. Una app en primer plano no implica cuenta lista para interacciones.

112 pruebas correctas: consolidación sin pérdida de fichas/identidades/snapshots, lectura de historia por referencia, rechazo de serial simultáneo distinto, metadatos incompatibles, cambio concurrente con rollback, migración de inventario antiguo y uso de alias en reasignación. También se reemplazaron rótulos fijos 2.13 del panel principal por la versión del paquete.
