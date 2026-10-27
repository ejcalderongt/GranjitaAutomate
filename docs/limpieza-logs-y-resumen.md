# Limpieza de logs y resumen de ejecución · v2.16

Fecha: 2026-10-26, America/Guatemala.

## Uso

Automatización tiene Limpiar logs en la barra inferior. También aparece en Logs y trazas. Archiva SQLite con su API de backup, verifica integridad y elimina los eventos anteriores al punto de corte. Si falla el respaldo, no elimina eventos. Los eventos nuevos posteriores al corte se conservan.

No borra tareas, recetas, métricas, resultados, feedback ni el log bruto de Appium. No se cambia ninguna cuenta ni se ejecutan tareas. Se bloquea si hay tareas Ejecutando, En cola o Programado; el panel también bloquea el botón mientras tiene un trabajador activo. Procesos externos de inventario pueden volver a generar eventos: cero es el estado del instante de limpieza, no una suspensión de las trazas.

Respaldo privado en data/backups/traces-antes-limpiar-*.sqlite3 y registro de corte en data/log-cleanups.jsonl. No se respaldan estos datos privados en Git. No se pide confirmación adicional porque la acción incluye archivo previo y fue autorizada por el usuario.

CLI equivalente:

```powershell
.\.venv\Scripts\python.exe -m scripts.diagnostics --clear
```

## Resumen visible

El indicador aparece encima de las pestañas. Distingue LOTE EN EJECUCIÓN, LOTE PROGRAMADO, LOTE PENDIENTE y LOTE TERMINADO. Terminado puede indicar Correcto, Con cancelaciones o Requiere revisión: no equivale a éxito completo.

Para preparación de apps muestra abiertas de total, sin apertura confirmada, sin ejecutar y pendientes. Sin apertura confirmada no asegura que la app jamás haya abierto: indica que falta una comprobación positiva final. Los contadores son por dispositivo. Tareas con estado desconocido nunca se declaran terminadas.

## Evidencia real

Durante la implementación terminó el lote 48dfacb8-0648-4599-a01a-277fa5f1f795 de 29 dispositivos: 13 aperturas confirmadas, dos para revisar y 14 canceladas antes de iniciar. Un caso no confirmó primer plano y otro se canceló durante la preparación. La UI se revisó visualmente con estos resultados.

A las 19:35:04 GT se archivaron y limpiaron 35 393 eventos. Consulta directa posterior: cero eventos y 110 tareas conservadas. No se reejecutaron tareas. Las pruebas de desarrollo finalizaron antes de la limpieza real.

98 pruebas correctas: archivo, conservación de feedback y tareas, bloqueo con tareas activas, preservación ante fallo de acceso, eventos concurrentes posteriores al corte y resumen explícito de cierre con GUI. Sin migración de esquema.
