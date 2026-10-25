# Creador de tareas y recetas · v2.9

Fecha: 2026-10-24, America/Guatemala. El usuario aclaró que «desde–hasta» significa horario, no rango de publicaciones.

## Pantalla

La vista Tarea concentra selección y receta. Resultados y auditoría contiene contadores, historial y exportación; Herramientas conserva Automate y el flujo anterior. El encabezado muestra seriales físicos en línea, dispositivos aptos y seleccionados. En línea significa respuesta ADB comprobada, no Internet. Aptos excluye fichas ambiguas o sin serial inequívoco; se muestra una fila por ficha, conservando orden físico donde esté asignado.

Al abrir se consultan conexiones/seriales y se vuelven a comprobar cada 30 segundos mientras no hay otro trabajador activo. Hasta la primera comprobación el encabezado indica Pendiente de comprobación actual. También se valida antes de registrar/ejecutar una tarea; si falta alguno de los seleccionados se detiene para revisar, sin sustituirlo silenciosamente. Cada sesión vuelve a validar serial. Una placa que cambie de transporte durante una espera puede requerir conciliación y una nueva tarea; no se infiere identidad desde IP.

Selección rápida: cantidad (ejemplo 10) y Seleccionar cantidad, Todos o Ninguno, además de casillas individuales. Si hay menos aptos que la cantidad, se seleccionan los disponibles y el resumen muestra el número real. La selección vacía se conserva al refrescar; no se ejecuta sin dispositivos.

## Receta lab_like_flow

- Nombre editable.
- Máximo de tarjetas/likes por dispositivo: 1–12, límite del feed de Granjita Lab. No garantiza ese número de likes nuevos: algunas tarjetas pueden estar ya marcadas.
- Desplazar después de cada like: activado por defecto. Se verifica movimiento, o que se alcanzó el final del feed. Aun desactivado, localizar una tarjeta posterior puede requerir desplazamiento de navegación.
- Ejecutar ahora, o fecha/hora Desde y Hasta de Guatemala (UTC−6). Fin debe ser posterior, con ventana máxima de 24 horas.
- Resumen: N dispositivos × X tarjetas = hasta N×X verificaciones, ejecución secuencial.

Cada dispositivo recorre las tarjetas 01…X una vez. No repite vueltas indefinidamente para llenar el horario; termina antes si alcanza el máximo o agota el feed local. En cada tarjeta consulta el estado, marca solo si falta, verifica, guarda evidencia y ejecuta el scroll solicitado. El objetivo es un estado marcado, no alternar el botón.

Guardar receta JSON permite reutilizar nombre/parámetros/horario; no incluye identificadores privados de los dispositivos seleccionados. Las recetas de ejemplo sin datos reales están versionadas. Cada ejecución guarda la selección real, parámetros, horario y copia del perfil/receta en automation.sqlite3, mediante tasks, like_context y task_recipes. Los estados Programado, Ejecutando, Expirado, Completado, Cancelado o Revisar resultado se guardan junto a los eventos.

## Horario, pausa y cancelación

El programa y el panel deben permanecer abiertos, con el PC encendido. La espera ocurre en un trabajador, sin bloquear la interfaz, y admite cancelación. No hay servicio de Windows, activación del PC ni reanudación automática después de cerrarlo. Al volver a abrir, tareas programadas/pendientes anteriores se marcan Interrumpido; su receta permanece disponible para revisión. No se prometió ejecución después de apagar el servidor.

El límite horario se comprueba antes de iniciar la sesión y antes de nuevas interacciones. Un dispositivo que no alcanzó turno antes del fin queda Expirado, sin interacción. Una tarea parcialmente ejecutada conserva pasos y métricas y puede quedar Revisar resultado cuando vence el horario. Las operaciones Appium ya enviadas no se pueden retirar: pueden terminar después del límite; no se inicia otra interacción. La pausa aplica antes de la siguiente acción y no extiende el horario. Pausas prolongadas pueden hacer expirar una sesión Appium, dejando revisión en lugar de reintento silencioso.

La CLI valida/ejecuta recetas, pero no espera horarios futuros: registra No ejecutado si está fuera de la ventana. Usar el panel para programar y esperar.

## Auditoría y métricas

Para el nuevo flujo se cuenta por (tarea, tarjeta destino), no solo por tarea. Eventos started, observed, click_requested, verified, evidence y scroll contienen el target exacto lab_like_01…12. Eventos duplicados del mismo destino no inflan el contador. Los flujos anteriores mantienen su interpretación de una sola tarjeta. Programados sigue contando tareas; Procesados/Aplicados/Ya marcados/Sin confirmar cuentan tarjetas dentro de esas tareas. La auditoría exporta las interacciones además de receta, horario y contexto de cada dispositivo. No se ejecuta sobre redes sociales.

## Uso

1. Abrir Laboratorio Appium / Automate; esperar comprobación del encabezado.
2. Seleccionar la cantidad o marcar dispositivos concretos.
3. Definir nombre, máximo de likes por dispositivo y scroll.
4. Elegir ahora u horario inicio/fin. Guardar la receta si se desea reutilizar.
5. Ejecutar tarea. Consultar Resultados y auditoría; pausar/cancelar desde los controles inferiores.

Plantilla: recipes/lab-like-flow.json. Las recetas anteriores lab_like y lab_smoke siguen cargándose; sus parámetros avanzados se deshabilitan para evitar atribuirles funciones que no ejecutan.

## Validación

63 pruebas con salida 0: horario inicio/fin, expiración sin abrir dispositivo, espera antes de ejecutar, selección de diez, receta con UTC−6, parámetros acotados, dos destinos con scroll y agregación sin duplicar eventos.

Piloto real 665cf0f3-f71a-40f5-a730-c43ed337a3fd: tres tarjetas verificadas, dos likes nuevos, una ya marcada y tres eventos de scroll. Se conservaron preferencias anteriores. La interfaz fue renderizada y revisada con la selección de diez: en esa instantánea había 31 seriales en línea y 28 aptos, no un inventario permanente. No se disparó un lote de diez ni se esperó un horario futuro real durante esta prueba; los límites del horario se verificaron con pruebas controladas. Queda pendiente validar el horario elegido por el usuario con el programa abierto.
