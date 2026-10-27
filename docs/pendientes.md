# Pendientes

- [ ] Confirmar inventario y conexiones actuales de las placas.
- [ ] Confirmar activación de Panda VIP.
- [ ] Incorporar documentación y herramientas previas que el usuario identifique.
- [x] Definir y documentar el primer trabajo técnico: asistente de conexión v1 con SQLite.
- [x] Validar arquitectura y conexión principal: OTG mediante el proceso de Panda.
- [x] Localizar ADB de Panda y comprobar acceso no disruptivo al servidor local existente.
- [ ] Probar con el usuario el flujo físico OTG y la recuperación guiada de una placa desconectada o sin autorización.
- [ ] Integrar visualización opcional con scrcpy si se necesita además de Panda.
- [x] Corregir detección para combinar servidores ADB 5037 y 5038, conservar origen y evitar falsos desconectados entre servidores.
- [ ] Reconciliar los 41 registros de Panda con los 33 dispositivos accesibles detectados en ambos servidores.
- [x] Fase 2: implementar inventario detallado con evidencias, identidad interna independiente de IP e historial de cambios; ver docs/version-2.md. La asociación física entre transportes es manual y explícita.
- [x] Mostrar estado de servidores ADB, puertos, PID disponible y conexiones por servidor.
- [x] Proponer nombres por serial físico, preservar alias y verificar correspondencias antes de asociar cambios de IP.
- [ ] Revisar manualmente las fichas con serial repetido y la conexión con identidad en conflicto detectadas en v2.1.
- [ ] Validar docs/modelo-gestion-social.md y elegir primera plataforma/capacidad para el adaptador; proponer primero grupos y trabajos simulados.
- [ ] Evaluar piloto de tareas mediante ADB/Automate frente a agente Android propio en una aplicación de prueba.
- [x] Implementar primer laboratorio Appium/UiAutomator2 y comprobar lote de tres placas en la app local de prueba.
- [x] Instalar Automate oficial remotamente en una placa piloto y crear flujo mínimo de apertura del laboratorio.
- [ ] Resolver con el usuario los permisos solicitados por Automate, ejecutar y verificar el flujo mínimo antes de ampliar sus tareas.
- [x] Consultar la API Android documentada de Panda y mostrar correspondencias de inventario desde la aplicación.
- [x] Crear perfil y receta JSON reproducibles con previsualización y ejecución tipada de laboratorio.
- [x] Completar auditoría final de propagación: cinco paquetes en las 33 conexiones accesibles; los permisos de Automate siguen separados de la instalación.
- [ ] Fase 3: definir proveedor de IA, manejo de credenciales, contexto permitido y ejecución supervisada.
- [x] Implementar conciliación al iniciar, apertura de Panda, reintentos acotados y activos primero con diagnóstico.
- [ ] Probar recuperación tras apagado completo de PC/rack; verificar si requiere botón físico y configuración OTG persistente.
- [ ] Identificar marca/modelo/controlador del rack, mapear ranuras a seriales y verificar telemetría de energía por canal.
- [ ] Obtener enlace/ASIN del chasis anunciado como «20-phone farm»; el usuario no encuentra marca/modelo físico. No asumir API eléctrica por apariencia.
- [x] Aclarar prueba de las 17:00 GT: el usuario confirmó que no regresaron 30 y 65; 51 sí recuperó imagen e Internet.
- [ ] Diagnosticar pantallas 30 y 65; registrar rack y verificar seriales para posiciones 10→65, 17→30 y 20→51. Correspondencias confirmadas por el usuario, aún no verificadas por serial.
- [ ] Obtener leyenda de indicadores del rack; posición 20/pantalla 51 reportada con Internet e indicador azul, por lo que azul no equivale a falla.
- [x] Implementar orden físico permanente por serial, asignación verificada y vista opcional de activos primero (v2.5).
- [ ] Completar mapa físico rack/posición/serial y elegir números Panda libres; aplicar desde el diálogo y comprobar persistencia tras reiniciar Panda.
- [x] Subfase 4.2: snapshots lógicos y archivos propios en SQLite, verificación/recuperación inicial de ausentes, historial y CLI; v2.6.
- [ ] Probar recuperación 4.2 tras apagado completo y arranque real del rack; confirmar cobertura de fichas que hoy tienen identidad ambigua o están desconectadas.
- [ ] Definir archivos/puntos de control útiles para las tareas; incorporar captura posterior a tareas y política de retención/backups externos. Actualmente se captura al crear base o por acción explícita.
- [ ] Evaluar adaptadores de exportación/importación de datos internos de apps específicas; no existe respaldo integral Android ni restauración de sesiones en 4.2.
- [x] Crear flujo básico lab_like reproducible en Granjita Lab, con selección, verificación y resultados SQLite.
- [ ] Validar un lote elegido por el usuario con el flujo solo Me gusta; no confundir estado ya marcado con una interacción nueva.
- [x] Guardar métricas estructuradas y destino por tarea lab_like, indicadores globales y auditoría exportable en JSON (v2.8).
- [x] Simplificar creador de tareas con selección por cantidad, indicadores de conectividad, likes por dispositivo, scroll y horario inicio/fin GT (v2.9).
- [ ] Validar una tarea con horario futuro elegido por el usuario, manteniendo PC y panel abiertos; las pruebas de límites ya están automatizadas.
- [x] Simplificar pantalla principal con pasos numerados, menú Avanzado, indicadores grandes y tooltips; nombres Snapshots y Automatización (v2.10).
- [x] Agregar trazas finas correlacionadas en SQLite, visor/exportación y feedback por ejecución (v2.11).
- [ ] Reunir muestras reales de duración/errores antes de ajustar tiempos o reintentos; medir costo de apertura Appium y clasificar incidentes a partir de trazas, sin contar errores anidados como placas fallidas.
- [x] Revisar trazas operativas y auditoría del lote; reforzar estabilidad/referencia del botón después del scroll sin repetir clics inciertos (v2.12).
- [ ] Comparar fallos del flujo estabilizado en nuevos lotes antes de afirmar reducción de errores; conservar pendientes los dos resultados históricos sin confirmar.
- [ ] Medir snapshots con concurrencia acotada de dos identidades; el inicio secuencial observado tomó unos 60 s.
- [ ] Distinguir listeners de forward/transporte de servidores host ADB antes de contar sus timeouts como incidentes operativos.
- [x] Agregar indicador visual de likes nuevos verificados e historial por dispositivo/destino, con filtros y exportación (v2.13).

- [x] Comparar activos Panda/ADB el 2026-10-26: coinciden 33 seriales físicos; ver docs/comparacion-panda-2026-10-26.md.
- [ ] Separar detectados de asociados/aptos en el indicador y revisar conflictos actuales de pantallas 06, 30, 46, 50, 51 y 65, conservando historial.

- [x] Resolver las siete conexiones en conflicto de 06, 30, 46, 50, 51 y 65 mediante serial actual verificado, respaldo y auditoría (2026-10-26).
- [ ] Revisar fichas históricas duplicadas de pantallas 04, 11, 28 y 62; hay 33 en línea y 29 aptos tras la reasociación. La separación visual detectados/aptos sigue pendiente.

- [x] v2.14: agregar app origen y preparación verificable para Granjita Lab/TikTok con auditoría SQLite y receta reproducible.
- [ ] Completar bienvenida/sesión de TikTok en placa de prueba y elegir publicación identificable; mapear y validar estado de like antes de habilitar el adaptador externo. Pantalla 06 solo tiene apertura comprobada.

- [x] v2.15: revisar último envío y distinguir en UI apertura completada, likes pendientes de mapeo, historial y cancelación; sin relanzar tareas.

- [x] v2.16: limpieza de trazas con archivo previo y resumen explícito del cierre y aperturas del lote; historial preservado.
- [ ] Agregar comprobación independiente posterior al lote: verificar nuevamente primer plano sin relanzar la app (solicitud siguiente del usuario).
