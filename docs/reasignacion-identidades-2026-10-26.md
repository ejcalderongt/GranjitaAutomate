# Reasociación verificada · 2026-10-26

Por instrucción del usuario se corrigieron las conexiones en conflicto sin acceso al router ni cambios de IP. Se conservan todas las fichas, alias, snapshots, checkpoints y tareas anteriores.

## Resultado a las 18:47 GT

- Siete conexiones reasociadas a seis fichas existentes, por serial actual único: Panda 06, 30, 46, 50, 51 y 65.
- El 46 tiene dos conexiones y cuenta como una placa.
- Verificados 33 seriales físicos en línea; conjunto idéntico a Panda.
- Cero conexiones en estado Identidad en conflicto.
- 29 fichas aptas para automatización. Las pantallas 04, 11, 28 y 62 siguen con Serial repetido: revisar por fichas históricas duplicadas; no se fusionaron en este trabajo.
- Integridad SQLite: ok. Nueva vista previa después de aplicar: cero reasociaciones pendientes.

## Procedimiento reproducible

```powershell
.\.venv\Scripts\python.exe -m scripts.reasignar_conflictos
.\.venv\Scripts\python.exe -m scripts.reasignar_conflictos --apply
```

La primera orden solo propone. La segunda consulta nuevamente Android y Panda, exige ficha destino única con serial, fabricante y modelo coincidentes, relee identidad antes de aplicar y verifica que la base no haya cambiado. Respalda SQLite con su API de backup y aplica todas las asociaciones en una transacción. No usa link_connection, que puede transferir observaciones y eliminar una ficha sin transportes: aquí el historial anterior permanece intacto.

Se registran eventos en ambas fichas y evidencia privada con estados prepared/committed, conexiones anterior/nueva y verificación final. Después se ejecuta un nuevo scan_fleet y se actualiza normalmente el inventario. Un error posterior al commit requiere consultar la auditoría antes de repetir; no se revierten cambios ciegamente.

Respaldo previo y auditoría JSON en data/ (excluidos de Git, contienen datos privados). El respaldo Git del procedimiento no incluye esas bases ni evidencias.

Para refrescar la ventana abierta, usar Conectar dispositivos. La base ya está actualizada; los indicadores en memoria necesitan una nueva lectura. No se cambia versión de UI: es mantenimiento del inventario y herramienta de soporte.

Validación: 77 pruebas correctas, incluidas cinco del plan (unicidad, desacuerdo con Panda, metadatos y ausencia de mutación). La ejecución real confirmó el conjunto de 33 y cero conflictos.
