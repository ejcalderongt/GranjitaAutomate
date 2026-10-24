# Diagnóstico: Panda muestra 41 y GranjitaAutomate 17

Fecha: 2026-10-23, America/Guatemala.

## Evidencia comprobada

- La captura aportada por el usuario muestra un grupo con 41 registros en Panda. Varias tarjetas indican explícitamente desconexión; 41 no demuestra 41 conexiones activas.
- Hay dos procesos adb escuchando en localhost, en los puertos 5037 y 5038.
- El servidor 5037 lista 17 dispositivos, todos en estado device.
- El servidor 5038 lista otros 16 dispositivos, todos en estado device.
- No hay identificadores coincidentes entre ambos conjuntos. Los 16 del puerto 5038 respondieron también a una consulta real de validación.
- Nuestra v1 consulta un solo puerto, 5037 por defecto. Por eso muestra 17; no es un límite de SQLite ni de la cantidad de consultas simultáneas.

## Conclusión y límite

Hay 33 dispositivos distintos accesibles entre los dos servidores en el momento del diagnóstico. La aplicación omite 16 porque no combina servidores.

La diferencia entre 41 registros de Panda y 33 dispositivos accesibles es 8. Es compatible con las tarjetas desconectadas, pero no se ha reconciliado el inventario completo de Panda para asegurar que sean exactamente esos ocho registros. Tampoco se ha verificado el propietario del ejecutable de cada servidor ni la conexión física OTG.

## Corrección propuesta

### Origen de los dos servidores

La inspección posterior de Win32_Process mostró que ambos procesos adb tienen el mismo ParentProcessId, correspondiente a touping (Panda), y la misma hora de creación. Esto confirma que los dos procesos fueron iniciados por Panda. Nuestra aplicación no ejecuta start-server.

La razón interna exacta por la que Panda divide los dispositivos entre servidores no pudo determinarse con la configuración y los registros revisados. El reparto observado de 17 y 16 dispositivos es compatible con gestión por grupos o reparto de carga, pero eso es una hipótesis, no una característica confirmada del fabricante. ADB utiliza normalmente el puerto 5037; el 5038 es una instancia adicional en este equipo.

Referencia del comportamiento normal de ADB: https://developer.android.com/tools/adb#how-adb-works

Consultar ambos servidores, conservar el puerto de origen para validar cada transporte, combinar el inventario y distinguir registros guardados de conexiones actuales. Si un dispositivo aparece por varios transportes, no asumir que son placas diferentes: la deduplicación física requiere un identificador estable verificado.

Cambiar manualmente el puerto a 5038 en la v1 permite ver el otro conjunto, pero no los suma y puede marcar el conjunto anterior como desconectado; no usar ese cambio como solución al inventario combinado.

## Reproducir

```powershell
.\.venv\Scripts\python.exe -m scripts.diagnosticar_adb
```

El diagnóstico imprime cantidades y estados, sin listar los identificadores privados. No reinicia servidores ni establece conexiones nuevas a placas.
