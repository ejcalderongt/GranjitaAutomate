# Indicador visual e historial de likes · v2.13

Fecha: 2026-10-24, America/Guatemala.

La pantalla principal muestra una tarjeta Likes logrados junto a los indicadores de dispositivos. En Automatización aparece un contador grande de 44 px, en verde, visible desde todas las pestañas, con acceso directo al historial. El contador refleja el total histórico de resultados applied verificados por (tarea, tarjeta). Excluye ya marcados, incertidumbre e históricos sin medición. No representa likes en una red social real ni publicaciones/usuarios únicos.

El contador del panel se actualiza al verificar una tarjeta y al finalizar tareas; el de la ventana principal se vuelve a leer al regresar de Automatización o actualizar la pantalla. Su consulta usa una conexión SQLite de solo lectura, sin inicializar JobStore ni alterar tareas ejecutándose. Si no hay base/historial estructurado se muestra 0; si la lectura falla, se muestra — y se registra el fallo.

## Historial

Pestaña Historial de likes: fecha/hora de Guatemala, dispositivo, dónde, resultado y tarea. Filtra por texto o por Logrados, Ya marcados, Sin confirmar e Históricos sin medición. Filas logradas en verde. Al seleccionar una fila se muestra referencia de tarea/lote, serial disponible, paquete/target y evidencia con hash si existe.

En el flujo actual se conoce el destino: gt.granjita.lab y lab_like_01…12; la tabla lo presenta como Granjita Lab · tarjeta 03. No existe URL externa que recopilar en esta aplicación local. Cuando falta contexto o destino se conserva No disponible. Los registros históricos sin medición no se convierten en nuevos likes por interpretar su texto. Las tareas aún sin iniciar permanecen en Resultados y auditoría y no crean una interacción ficticia en el historial.

El historial se deriva de tasks, like_context y like_events ya persistidos en automation.sqlite3, sin duplicar contadores en tablas nuevas. Se conserva al cerrar/reabrir. Exportar auditoría JSON incluye también la lista history con destino y evidencia. La base, exportaciones y capturas siguen fuera de Git.

## Validación

72 pruebas con salida 0, incluyendo deduplicación por tarea/tarjeta, total de solo lectura sin alterar una tarea Ejecutando y destino conservado en historial. Revisión visual con el estilo de la aplicación: 78 likes nuevos verificados, 14 ya marcados, 2 sin confirmar y un histórico sin medición en la instantánea consultada. 95 filas de historial, incluyendo los no confirmados e históricos. No se ejecutaron likes ni se modificaron estados reales para esta entrega. Los números son una instantánea del laboratorio, no un inventario ni un valor fijo del producto.
