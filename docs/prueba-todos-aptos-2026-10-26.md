# Prueba de todos los equipos aptos · 2026-10-26

Se repitió desde la ventana real de Automatización 2.19: Tarea → Todos → App origen TikTok → Abrir y comprobar app. La UI conservó 33 en línea y seleccionó los 29 aptos. No se usó el ejecutor CLI para lanzar tareas.

## Resultado

Lote 2d6ef9db-2f7d-4e7a-9304-edbf0faa22f4, creado 20:08:27 GT; segunda comprobación terminada 20:08:48 GT:

- 29 tareas completadas, sin canceladas ni resultados para revisar.
- 29 apps confirmadas en primer plano por la verificación posterior.
- Las 29 ya estaban abiertas (launched=false); no hubo relanzamientos en esta repetición.
- Cero eventos de error operativos vinculados a los task_id del lote.
- Conjunto de fichas ejecutadas igual a todos los aptos de SQLite en ese momento.
- Interfaz en verde con Lote terminado, 29/29 verificadas y cero para revisar/sin ejecutar.

Esta repetición demuestra detección/continuidad de apps ya abiertas; no prueba arranque en frío. La prueba anterior de 14 pendientes sí registró 13 lanzamientos y una app ya abierta (docs/prueba-apertura-ui-2026-10-26.md). No se deben presentar los 29 resultados actuales como 29 lanzamientos desde app cerrada.

## Cuatro equipos excluidos

Lectura independiente, sin lanzamiento ni cambios de asociaciones, de las fichas activas con Serial repetido: revisar:

| Pantalla Panda | ADB/serial actual | TikTok instalado | Primer plano observado | Incluida en lote |
|---|---|---|---|---|
| 04 | Responde y coincide con identidad declarada | Sí | Launcher Android | No |
| 11 | Responde y coincide con identidad declarada | Sí | Launcher Android | No |
| 28 | Responde y coincide con identidad declarada | Sí | Launcher Android | No |
| 62 | Responde y coincide con identidad declarada | Sí | Launcher Android | No |

El programa las excluye por identidad histórica ambigua; no se ha demostrado fallo de apertura TikTok en ellas porque no se envió la apertura. No se eludió el control de identidad ni se fusionaron fichas para ampliar el conteo. Informe privado de lectura en data/all-devices-excluded-readonly.json, fuera de Git.

## Alcance pendiente

Conciliar de forma auditable las cuatro identidades duplicadas para poder probar los 33 conectados dentro del panel. Los 39 registros de la captura Panda incluyen desconectados; la API list de activos no confirma por sí sola todos los registros guardados ni habilita pruebas sobre equipos inaccesibles.

Si se desea medir variantes de arranque real, planificar una prueba que parta explícitamente fuera de TikTok y verificar actividad/tiempo de lanzamiento. En esta ejecución no se cerraron apps ni se modificaron perfiles, permisos, bienvenida o sesiones; tampoco se ejecutaron likes. Se dejó el panel abierto en Resultados y auditoría.
