# Resumen compacto y última ejecución · v2.18

Fecha: 2026-10-26, America/Guatemala.

## Lectura de resultados

La última ejecución registrada al revisar sigue siendo 48dfacb8-0648-4599-a01a-277fa5f1f795, creada a las 19:29:54 GT. Sus 29 tareas de apertura TikTok terminaron con 13 completadas, dos para revisar y 14 canceladas antes de iniciar.

Un resultado para revisar corresponde a falta de confirmación de primer plano; el otro indica cancelación durante la preparación. No se atribuyen ambos a un fallo técnico ni se identifica quién solicitó la cancelación. La causa del primer caso (bloqueo, diálogo u otra condición) no está confirmada.

La segunda lectura guardada a las 19:39 GT confirmó 13 en primer plano, uno fuera de primer plano (launcher Android), uno sin actividad identificable y 14 sin ejecutar/omitidos. No hubo likes ejecutados en este lote de preparación.

Los logs de ejecución originales fueron archivados durante la limpieza autorizada; la consulta de trazas actual no contiene errores vinculados a ese lote. Su ausencia no invalida los resultados de revisión guardados en SQLite ni demuestra ausencia de incidentes históricos. Este diagnóstico combina tasks y app_verifications; no se relanzaron tareas ni se volvió a abrir una app.

## Indicador simplificado

El recuadro muestra únicamente:

- Encabezado: estado del lote y app.
- Tres columnas grandes: apps verificadas / total, para revisar y sin ejecutar.
- Pie: estado y hora de la verificación.

Con los resultados revisados: Lote terminado · TikTok; 13/29 apps verificadas, dos para revisar y 14 sin ejecutar; verificación terminada. El detalle original permanece en tabla, ficha y tooltip al pasar por el indicador. El mensaje de cierre inferior también se redujo a una línea.

Cuando existe verificación posterior, la cifra confirmada proviene de esa lectura, aunque la apertura original hubiera sido exitosa. Una app observada después fuera de primer plano no conserva una confirmación antigua en el resumen. Una comprobación aún en curso muestra Verificando ejecución y su avance, sin declararse terminada.

103 pruebas correctas y revisión visual del panel con datos actuales. Sin migración SQLite ni cambios de métricas, tareas, resultados o verificaciones. Los límites de TikTok continúan descritos en docs/app-origen.md.
