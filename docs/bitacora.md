# Bitácora

## 2026-10-23

- Se recuperó el contexto disponible de los chats sobre Panda VIP y ADB.
- Se vinculó la carpeta de trabajo AGX con el repositorio GranjitaAutomate.
- Se creó la estructura inicial de documentación y las instrucciones de mantenimiento.
- No se ejecutaron cambios sobre las placas Android.
- Se documentó una propuesta inicial de asistente de conexión con Python, PySide6, ADB y scrcpy opcional. Falta confirmar conexión física y versiones Android; la tecnología aún no fue aprobada por el usuario.
- Posteriormente el usuario aprobó la arquitectura y confirmó OTG mediante el proceso de Panda como conexión permanente deseada. Se actualizó la propuesta; queda pendiente verificar la integración técnica con Panda.
- Se construyó v1 con PySide6 y SQLite portable: detección y validación asíncronas, inventario, alias, historial, reintentos guiados, revisión periódica opcional, apertura de Panda y respaldo SQLite.
- Se confirmó comunicación real con 17 dispositivos Android 12 mediante el servidor ADB local, sin reiniciarlo. Se evita ejecutar un cliente ADB de otra versión.
- Los accesos observados son TCP/IP, por lo que la conexión física OTG no se da por validada. Se añadió la distinción a la interfaz.
- Se creó el acceso directo del escritorio y se verificó la interfaz con las 17 placas. Pasaron cinco pruebas de protocolo, autorización, tiempo límite, inventario, persistencia de alias y respaldo SQLite.
- Se diagnosticó la diferencia Panda 41 / aplicación 17: existen dos servidores ADB, con 17 y 16 dispositivos distintos respectivamente, en 5037 y 5038. Se validaron los 16 del segundo servidor. Falta soporte de inventario combinado y reconciliar los registros desconectados de Panda. Se guardó un diagnóstico reproducible sin identificadores privados.
- Se confirmó por los procesos padre que Panda (touping) inició ambos procesos adb a la misma hora. El motivo interno del reparto sigue sin confirmarse; gestión por grupos o carga es solamente una hipótesis.
- El usuario definió fase 2 (inventario detallado) y fase 3 (tareas e interpretación contextual mediante IA en cuentas controladas). Se registró la hoja de ruta y la propuesta de evaluar ADB/Automate antes de un agente Android propio. No se instalaron agentes ni se ejecutaron interacciones en cuentas.
- Se implementó v2: panel de servidores/puertos/PID, agregación de conexiones, búsqueda, fichas de inventario con 34 observaciones, evidencia y cambios, asociación física explícita y manejo de fallos parciales.
- Se migró SQLite con respaldo previo y conservación de alias/eventos. Se inventariaron 33 conexiones. En 14 se observó su y en 19 no, sin ejecutar su ni confirmar ausencia de root.
- Pasaron once pruebas automatizadas y se revisaron visualmente la ventana y la ficha de inventario.

## 2026-10-24

- Se implementó v2.1 con nombres automáticos basados en serial físico, columna separada de identidad, conservación de alias y asociación conservadora después de cambios de IP.
- Se agregó respaldo previo a migración SQLite v3, recuperación de seriales de capturas existentes y alertas por seriales repetidos o cambios de identidad en una IP.
- Pasaron 15 pruebas y se verificó la interfaz con datos reales. Se observaron un serial compartido entre dos fichas y una conexión con identidad en conflicto; no se fusionaron ni sobrescribieron automáticamente.
- Se incorporó a AGENTS.md la instrucción de hacer commit y push después de cada avance funcional verificado.
- Se documentó una propuesta de gestión social con cuentas separadas de placas, grupos, trabajos persistentes, estadísticas verificables, adaptadores API y ejecución Android de laboratorio. Se recomienda Appium/UiAutomator2 para el piloto y evaluar Automate para flujos sencillos. No se instalaron herramientas ni se ejecutaron acciones sociales.
- Se preparó el laboratorio Appium 3.8.0/UiAutomator2 8.7.0, SDK aislado con ADB de Panda y APK local sin INTERNET. Pasó una prueba real de like, comentario y scroll en una placa; el lote entre servidores sigue en estabilización. Se aprobaron 20 pruebas automatizadas. El usuario autorizó intentar instalar Automate remotamente desde Google Play.
- Se completó el lote real de tres placas con ambos servidores ADB, verificando like, comentario y scroll locales. Se estabilizó la APK y su actualización con instalación explícita preservando datos. Los procesos ADB de Panda mantuvieron sus PID.
- Se agregó el panel de laboratorio a v2.2 con selección por identidad, lotes secuenciales, pausa/cancelación, resultados e historial SQLite separado. Se revisó visualmente y se aprobaron nuevamente 20 pruebas.
- Se instaló remotamente Automate oficial en una placa piloto y se creó el flujo Granjita Lab - abrir laboratorio. La ejecución quedó pendiente de autorización para tres privilegios que solicita Automate; no se concedieron. Se conservó el flujo configurado.
- Se implementó propagación verificable de los cinco APK, conservando datos y sin conceder permisos. Se verificó una pasada completa de 30 fichas; la ampliación a tres transportes adicionales usa coincidencia actual de getprop y onlySerial de Panda sin alterar asociaciones históricas.
- Se comprobó la API Android oficial de Panda por WebSocket local: 33 registros en modo OTG con onlySerial. Se agregó adaptador de lectura y panel de comparación; no se enviaron cambios de nombres, grupos o ajustes por la API.
- Se agregaron perfiles y recetas JSON versionables, validación, ejecución local explícita y copia inmutable con hash por tarea. Se aprobaron 30 pruebas, incluyendo trabajadores de los diálogos de laboratorio y Panda API.
- Auditoría final: los cinco paquetes están instalados en las 33 conexiones accesibles, incluidas tres verificadas por coincidencia de Panda onlySerial y getprop. No se copiaron datos de cuentas ni se otorgaron permisos de Automate.
- Se completó una receta JSON real de laboratorio y se verificó su almacenamiento inmutable con hash. Se agregó carga de recetas en el panel. V2.3 incluye API Panda de lectura y guía de perfiles/recetas.
- Se aprobaron 33 pruebas con código de salida 0. Se ajustó la liberación de trabajadores Qt y la limpieza de las pruebas de interfaz para evitar un fallo al cerrar el proceso de pruebas.

## 2026-10-24 · Arranque y conciliación v2.4

Se agregó apertura de Panda cuando falta, reconexión acotada de transportes conocidos, comparación con API, activos primero y en verde, diagnóstico por fila y resumen separado de seriales/transportes. Se corrigió la duplicación de candidatos detectada durante la prueba real. Se inspeccionó USB de Windows sin identificar telemetría eléctrica por ranura. Ver docs/arranque-y-rack.md; no se realizó apagado físico y no se atribuyen fallos de energía sin medición. Validación: 37 pruebas con salida 0 y comprobación del panel.

## 2026-10-24 · Referencia visual del chasis

El usuario no observa marca/modelo. Se registró la variante visible «20-phone farm» y los límites de identificación; las publicaciones semejantes no prueban fabricante ni capacidades eléctricas. Pendiente enlace/ASIN o etiquetas/conexiones externas para identificar controlador. No se almacenaron capturas privadas del pedido ni se cambiaron configuraciones de las placas.

## 2026-10-24 · Prueba física de posiciones 10, 17 y 20

Se registraron correspondencias reportadas con pantallas 65, 30 y 51. La posición 20/pantalla 51 recuperó imagen e Internet según operador aunque sigue azul; no usar color como diagnóstico de conectividad. Recuperación requirió Habilitar/Escanear en Panda. Hay contradicción sobre las dos pantallas que no regresaron, pendiente aclaración. Falta identificador de rack y seriales; no se modificaron asociaciones del inventario ni se guardó la foto.


## 2026-10-24 · Aclaración de recuperación física

El usuario confirmó que las pantallas ausentes son 30 (posición 17) y 65 (posición 10). La 51 (posición 20) recuperó imagen e Internet según el reporte. Se resolvió la contradicción documental; sin nueva prueba remota ni diagnóstico eléctrico.

## 2026-10-24 · Orden físico v2.5

Se implementó mapa rack/posición/serial con número Panda único, vista fija predeterminada y activos primero opcional. Una fila por ficha evita duplicar sus transportes. La asignación verifica getprop y bloquea identidades ambiguas. La aplicación individual de nombre/número a Panda comprueba identidad, colisiones y lectura posterior, y conserva evidencia local. Migración SQLite v4 con respaldo. Sin asignaciones físicas inventadas ni renombres reales todavía: faltan rack y seriales verificados. Validación: 41 pruebas con salida 0 y panel revisado. Guía: docs/orden-fisico.md.

## 2026-10-24 · v2.6, subfase 4.2: snapshots

Se agregaron manifiestos, archivos BLOB con hashes y eventos de recuperación a granjita.sqlite3 (migración v5 con respaldo). Tras la conciliación inicial se crea base si no existe o se verifican/recuperan solo archivos propios ausentes. Archivos diferentes e inventario se comparan sin revertir datos recientes o ajustes. Panel y CLI incluidos; no se reanudan tareas inciertas ni se respaldan sesiones/datos internos de apps ajenas. 50 pruebas pasan con salida 0. Captura actualizada completa en 28/28 fichas elegibles; errores del intento con transportes obsoletos quedaron registrados. Recuperación real de un JSON propio verificada byte por byte. Integridad SQLite correcta. Sin prueba de corte completo del rack. Guía detallada: docs/subfase-4-2-snapshots.md; índice: docs/versiones.md.

## 2026-10-24 · v2.7: primer flujo básico de likes

Se agregó lab_like con receta local reproducible y acceso directo dentro del panel de laboratorio. Lee el estado, solo pulsa si falta y confirma SI; no comenta ni desplaza. Guarda acción y receta/perfil en SQLite, evidencia local y resultados inciertos sin reintento. 53 pruebas pasan. Ver docs/flujo-likes.md.

## 2026-10-24 · v2.8: métricas auditables de likes

Se agregaron contexto inmutable y eventos de ejecución a automation.sqlite3, contadores globales por tarea, detalle de destino y exportación JSON con receta/perfil y evidencia referenciada por SHA-256. Se separan aplicados de ya marcados y resultados sin confirmar; no se infieren resultados históricos desde texto. Respaldo previo a agregar las tablas. 56 pruebas pasan. Ver docs/metricas-likes.md.

Piloto auditado 72a2a356-18f4-4896-9ecd-ab0229a92568 completado: 1 procesado, 0 aplicados nuevos, 1 ya marcado, 0 sin confirmar. El piloto anterior permanece histórico sin medición estructurada. Se verificó SHA-256 de evidencia y exportación local JSON.

## 2026-10-24 · v2.9: creador de tareas, horario y scroll

Se simplificó el panel en Tarea, Resultados y auditoría y Herramientas. Encabezado con en línea/aptos/seleccionados, selección por cantidad, refresco real antes de ejecutar, receta de máximo de tarjetas por dispositivo y scroll tras cada like. Desde–Hasta representa fecha/hora GT, según aclaración del usuario. Ventana y parámetros persistidos con selección real en SQLite; sin reanudación tras cierre. Métricas por tarjeta con destino exacto. 63 pruebas pasan y piloto real de tres tarjetas completado: dos likes nuevos, una ya marcada, tres scrolls. No se ejecutó lote de diez ni horario futuro real. Guía: docs/creador-tareas.md.

## 2026-10-24 · v2.10: pantalla principal guiada

Se organizaron tres pasos visibles: conectar/comprobar, revisar/elegir y preparar/ejecutar. Snapshots y Automatización reemplazan los rótulos técnicos. Se movieron nombres, inventario, mapa físico, ADB/API, preferencias y respaldo a Avanzado. Cuatro indicadores de cantidad grandes, tooltips y tabla simplificada con columnas técnicas opcionales. Sin alterar lógica de tareas ni asociaciones. Revisión visual con estilo real y 63 pruebas existentes correctas. Guía: docs/ui-principal.md.

## 2026-10-24 · v2.11: trazas finas y feedback

Se instrumentaron Panda, ADB, inventario, snapshots, identidad y Appium con tiempos, contexto por dispositivo/tarea y correlación entre hilos. Base SQLite independiente con retención acotada, visor Avanzado → Conexión y diagnóstico → Logs y trazas, exportación y feedback observado/esperado. Sin cuerpos, salidas ni mensajes brutos en la traza. Se corrigió separación de eventos de tests para no confundirlos con fallas reales, preservando copia anterior. Validación: 68 pruebas, búsqueda real con 222 eventos correlacionados, piloto local completado con 37 eventos vinculados a tarea y exportación, nota técnica persistida e integridad SQLite correcta. Primer dato: apertura de sesión 5.3 s sobre tarea de 8.2 s, una sola muestra. Guía: docs/logs-y-feedback.md.

## 2026-10-24 · v2.12: revisión de resultados y estabilidad del flujo

Se cruzaron trazas reales con el lote histórico de 28 placas: 26 tareas completas y 2 para revisar; 81 tarjetas verificadas (76 likes nuevos, 5 ya marcados), 2 sin confirmar y 1 sin iniciar. No se reejecutaron las tareas inciertas. Se reforzó la estabilidad del botón y su referencia después del scroll, con verificación solo de lectura ante una vista recreada. Nuevos tiempos separados para instalación y creación Appium. 71 pruebas y piloto real de tres tarjetas ya marcadas correctos; no se atribuye mejora de velocidad ni resolución definitiva de los fallos. Snapshots iniciales medidos en 59.8 s; paralelismo acotado queda propuesto. Informe y reproducción: docs/revision-logs-2026-10-24.md y scripts/review_results.py.
