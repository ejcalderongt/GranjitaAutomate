# Propuesta: centro de operaciones de cuentas y dispositivos

Fecha: 2026-10-24. Propuesta de arquitectura; sin ejecución de tareas sociales ni instalaciones nuevas.

## Objetivo y experiencia

Evolucionar GranjitaAutomate con cinco áreas: Inicio, Dispositivos, Cuentas, Trabajos y Resultados. La operación por lote se organiza como un trabajo con objetivo, cuentas participantes, contexto, acciones disponibles, vista previa y resultado verificable por participante.

Una cuenta es una entidad independiente de la placa y de su IP. Registrar plataforma, identificador público autorizado, dispositivo/perfil asignado, estado de acceso y capacidades disponibles; las credenciales van en un almacén protegido externo a SQLite y Git.

## Componentes

1. Interfaz PySide6 existente: selección de grupos, asistente de trabajo y visualización de progreso.
2. SQLite: dispositivos/conexiones actuales más accounts, device_account_assignments, groups, jobs, job_targets, attempts, evidence_refs y metric_samples. Esto es diseño propuesto, no esquema migrado.
3. Planificador persistente: cola por dispositivo y cuenta, bloqueo para evitar dos tareas simultáneas sobre una misma interfaz, pausa/cancelación y recuperación después de reiniciar.
4. Adaptadores de plataforma: API oficial para publicaciones, comentarios y métricas que cada producto permita, con permisos y capacidades explícitos. Una capacidad técnica de pulsar un botón no implica que la plataforma admita automatizarlo.
5. Ejecutor Android de laboratorio: Appium + UiAutomator2 para pruebas de interfaz reproducibles con selectores y comprobaciones de estado. Evaluar Automate como piloto de flujos locales sencillos, no como base obligatoria de todo el sistema.
6. Servicio de contexto: interpreta objetivo y contenido, prepara borradores y explica la propuesta. El motor de tareas valida los parámetros; la IA no recibe ejecución arbitraria ni credenciales de las cuentas.

No instalar una APK propia inicialmente. Considerar un agente Kotlin cuando la operación deba continuar autónomamente sin el PC o se requiera telemetría que los adaptadores no cubran. Investigar coexistencia con los dos servidores ADB de Panda antes de abrir sesiones Appium; no iniciar un ADB diferente que interrumpa Panda.

## Flujo de trabajo

Elegir entorno y plataforma → seleccionar grupo de cuentas → definir objetivo → preparar contexto y vista previa por cuenta → revisar → ejecutar las acciones admitidas → verificar → consolidar resultados.

Un lote contiene tareas individuales, no un broadcast ciego de toques. En laboratorio, acciones como desplazarse, marcar una publicación de prueba o enviar un comentario de prueba deben comprobar la cuenta, el contenido objetivo, el estado previo y el resultado. Publicar una respuesta a un comentario recibido y autorizado es un caso de gestión distinto a hacer reaccionar múltiples cuentas sobre la misma publicación.

Estados: borrador, preparado, pendiente de revisión, en cola, ejecutando, completado, fallido, resultado incierto, pausado y cancelado. Usar identificador de idempotencia por acción; si una respuesta se pudo publicar pero no se verificó, consultar su estado antes de reintentar. No resolver incertidumbre repitiendo comentarios.

## Estadísticas

- Operación: conexiones verificadas, fichas sin conflicto, tareas pendientes, éxito/fallo, latencia, disponibilidad y causas de error.
- Contenido: publicaciones y respuestas verificadas, tiempos de atención y borradores aprobados/rechazados.
- Red social: alcance, impresiones e interacciones orgánicas únicamente cuando las API autorizadas las suministren. Guardar fuente, periodo y fecha; no inferir esas métricas a partir de toques enviados.
- IA: solicitudes, consumo/costo cuando el proveedor lo informe, latencia y revisión humana.

Separar siempre métricas reales y resultados del laboratorio.

## Límites concretos de integración

La documentación vigente consultada de X prohíbe los likes automatizados y la automatización fuera de su API. Las respuestas automáticas con IA requieren aprobación escrita y explícita de X. Por ello, un flujo de likes en lote sobre X no debe presentarse como función disponible; el laboratorio puede reproducirlo en una aplicación de prueba propia. Para otras plataformas se evaluarán las capacidades y reglas concretas antes de habilitar un adaptador.

Tener cuentas propias o controladas no habilita automáticamente todas las formas de automatización de una plataforma.

## Próximo incremento propuesto

1. Grupos de dispositivos/cuentas y panel operativo con datos existentes, sin simular estadísticas sociales.
2. Motor de trabajos con ejecución simulada, pausa, cancelación e historial persistente.
3. Piloto en una placa y aplicación de prueba, usando Appium para abrir, localizar contenido, desplazarse y verificar una acción.
4. Ampliación a tres placas después de probar aislamiento de sesiones, compatibilidad ADB, idempotencia y resultados.
5. Primer adaptador de API para una plataforma/capacidad elegida; después incorporar contexto de IA y borradores revisables.

## Fuentes consultadas

- Appium UiAutomator2: https://appium.github.io/appium-uiautomator2-driver/
- Automate Interact: https://llamalab.com/automate/doc/block/interact.html
- Automate Flow beginning: https://llamalab.com/automate/doc/block/flow_beginning.html
- X Automation rules: https://help.x.com/en/rules-and-policies/x-automation
