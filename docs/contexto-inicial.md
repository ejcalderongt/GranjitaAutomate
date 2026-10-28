# Contexto inicial de GranjitaAutomate

Actualizado: **2026-10-28, America/Guatemala**. Punto de entrada para retomar el proyecto sin releer todo el chat. Resume evidencia; no sustituye el código ni una consulta actual a los equipos.

## Lectura mínima al iniciar

1. Leer `AGENTS.md`, este archivo y `README.md`.
2. Ejecutar `git status --short` y revisar cambios locales antes de editar; consultar `git log -5 --oneline`.
3. Elegir la guía temática de la tabla inferior. Leer bitácora solo para investigar antecedentes.
4. Consultar dispositivos/logs actuales únicamente si la tarea lo requiere. Los números siguientes tienen fecha y **no son disponibilidad en vivo**.

## Propósito y preferencias del usuario

Administrar una granja de placas Android desde una app Windows amigable, intuitiva y progresiva, con inventario fino, estado de conexiones, recetas, estadísticas y auditoría. Mantener OTG mediante el proceso de Panda, SQLite portable y acceso directo. Reducir intervención humana mediante comprobaciones fiables, no asumir éxito por enviar un comando.

El repositorio es la memoria persistente del trabajo. El usuario pide documentar versiones y aprendizajes y hacer **commit y push a origin/dev2026 tras cada avance funcional verificado**. Prefiere ejecutar y comprobar el trabajo autorizado, con actualizaciones claras en español. UI: pasos numerados, botones simples, funciones expertas en Avanzado, tooltips, cifras grandes, activos primero y cierre explícito de lotes. No necesita repetir estas preferencias en cada conversación.

## Entorno y estado del software

- Repositorio: https://github.com/ejcalderongt/GranjitaAutomate.git; rama de trabajo solicitada: `dev2026`, no master; sin push forzado.
- Workspace conocido: `C:/Users/labor/OneDrive/Documents/ChatGPT/AGX`. Resolver rutas desde el repositorio; no asumir que otra máquina comparte esta ubicación.
- Versión implementada: **2.21.0**, último avance funcional de referencia `71d3d9f`. Confirmar `granjita/__init__.py` y Git al retomar.
- Python + PySide6, cliente ADB por socket, SQLite, Appium + UiAutomator2; Granjita Lab es APK propia de pruebas. Automate es complemento, no requisito de todos los flujos.
- Acceso directo conocido: **GranjitaAutomate**. `iniciar.vbs` ejecuta `.venv/Scripts/pythonw.exe -m granjita`. El panel puede abrirse desde el paso 3: Apps y cuentas, Snapshots, Automatización.
- Panda observado: v9.12.213; instalación conocida `C:/Program Files (x86)/panda_android/touping.exe`. API local WebSocket `ws://127.0.0.1:22222/`. Appium observado en localhost:4723. Son configuración histórica, comprobar si dejan de responder.
- Última suite registrada: **131 pruebas correctas, 2026-10-27**. No se repitió por la actualización documental del 28.

## Arquitectura, datos y navegación del código

| Responsabilidad | Archivos / guías |
| --- | --- |
| UI principal y acceso ADB/SQLite | `granjita/app.py`, `core.py`, `inventory.py`; [inventario](version-2.md) |
| Conciliación de inicio y servidores | `reconciliation.py`; [arranque](arranque-y-rack.md), [diagnóstico ADB](diagnostico-servidores-adb.md) |
| Identidad canónica e historia | `identity_consolidation.py`, `physical.py`; [consolidación](consolidacion-identidades.md), [orden físico](orden-fisico.md) |
| Inventario y comparación Panda | `panda_api.py`, `panda_ui.py`; [API y recetas](api-panda-y-recetas.md) |
| Trabajos, recetas, app origen | `automation.py`, `automation_ui.py`, `recipes.py`, `taskflow.py`, `app_sources.py`; [tareas](creador-tareas.md), [app origen](app-origen.md) |
| Resultados y comprobación posterior | `task_results.py`, `like_history.py`; [verificación](verificacion-posterior-apps.md), [métricas](metricas-likes.md) |
| Logs y feedback | `diagnostics.py`, `diagnostics_ui.py`; [trazas](logs-y-feedback.md), [limpieza](limpieza-logs-y-resumen.md) |
| Snapshots lógicos | `snapshots.py`, `snapshots_ui.py`; [subfase 4.2](subfase-4-2-snapshots.md) |
| Apps y cuentas | `app_inventory.py`, `app_inventory_ui.py`; [guía v2.21](inventario-apps-y-cuentas.md) |

Las rutas de código de la tabla son relativas a `granjita/`. `scripts/` contiene CLI reproducibles; `tests/` las pruebas; `profiles/` y `recipes/` las plantillas versionadas. [Versiones](versiones.md) enumera las entregas; [bitácora](bitacora.md) conserva la cronología; [contexto original](contexto.md) documenta el comienzo.

SQLite local y evidencias están en `data/`, excluido de Git. El inventario usa `granjita.sqlite3` (comprobar ruta definida en código); tareas/auditoría de automatización usan `automation.sqlite3`. El esquema del inventario es **7**. Tablas clave: `device_identity`, `device_identity_aliases`, `physical_positions`, snapshots/checkpoints, `device_app_observations`, `device_app_assignments`. Las migraciones crean respaldo previo. No borrar ni reescribir historia para arreglar una identidad. No editar la base mientras procesos estén escribiendo sin coordinarlo.

Git respalda código y documentación, **no** las bases, APK, capturas, trazas ni respaldos privados de `data/`. Falta política de respaldo externo privado. No versionar contraseñas, cookies, tokens, códigos VIP, identificadores privados de cuentas ni capturas que los revelen.

## Identidad y conectividad: aprendizajes esenciales

- Se observaron servidores ADB **5037 y 5038**. Una placa puede aparecer en ambos. Conservar el servidor de origen; contar identidades físicas, no conexiones ni procesos/listeners.
- No iniciar otro ADB ni matar/reiniciar los existentes como primera medida: puede interrumpir Panda. El cliente por socket reutiliza los existentes.
- IP:puerto es transporte variable; no es identidad permanente. La clave operativa combina UUID canónico y serial físico verificado; contrastar Android/getprop, fabricante/modelo y `onlySerial` de Panda ante conflictos. Una IP reutilizada no permite trasladar automáticamente la historia.
- El usuario no tiene acceso al router; no se estableció una política de IP fija. No cambiar redes para resolver duplicados de ficha.
- El número Panda es referencia de pantalla, no serial ni posición permanente. Mapear rack/ranura/serial explícitamente y conservar alias. La declaración manual de cuentas conserva el número Panda al momento del reporte.
- La API `list` comprobada devolvía activos, mientras la UI de Panda conservaba fichas desconectadas. **39 guardados no equivale a 39 en línea**; 41 y 17 fueron cifras anteriores de otro momento.
- El 2026-10-26 Panda y ADB coincidieron en **33 identidades físicas**. Tras reasociación de siete conexiones de seis placas y consolidación histórica de **04, 11, 28, 62**, quedaron **33 en línea/aptos**, sin borrar snapshots ni auditoría. No asumir ese estado hoy sin nueva consulta.
- Se preservaron las fichas históricas mediante alias al UUID canónico más antiguo. No repetir consolidaciones a ciegas ni inventar seriales. CLI de diagnóstico/consolidación tiene validación previa.

## Apertura, tareas, métricas y aprendizajes de pruebas

Implementado: recetas tipadas con copia/hash, selección por identidad, horarios inicio/fin de Guatemala, pausa/cancelación, trazas y resultados por dispositivo. No ejecutar shell arbitrario desde recetas. El horario requiere PC/panel abiertos; falta validar recuperación de trabajos tras reinicio completo.

El perfil TikTok localiza paquetes admitidos, abre si corresponde y verifica primer plano. Una corrección soportó `ResumedActivity` sin prefijo `m`; antes causaba falsos negativos. No confundir una app abierta con feed listo, cuenta autenticada o tarea completada.

Último lote real de apertura completo documentado: **2026-10-26, 20:22 GT**, ID `de85e30c-c095-4978-85aa-ceb360a0d57f`: **33 completados y 33 verificados posteriormente**, cero errores ligados; cuatro lanzamientos y 29 ya abiertos. No hubo likes ni login ni elecciones de onboarding. La repetición de apps ya abiertas no prueba arranque en frío. Detalles: [consolidación](consolidacion-identidades.md) y [pruebas previas](prueba-todos-aptos-2026-10-26.md).

La comprobación posterior corre en otro trabajador y relee identidad/primer plano sin relanzar. Conservar resultado original y verificación posterior por separado. Contar lotes/tareas, no eventos anidados, al calcular fallos. Logs limpiados se archivan antes; limpiar trazas no elimina historial de tareas.

Likes verificables existen en **Granjita Lab**, con distinción nuevo / ya marcado / sin confirmar. La estabilidad del elemento después de scroll y la relectura evitan repetir clics inciertos. Una orden enviada no es un like confirmado. Resultados inciertos no se reintentan ciegamente; no contar interacciones del laboratorio como métricas de redes sociales.

## Apps y cuentas: v2.21

Separar cuatro hechos: instalación técnica; cuenta esperada asignada; cuenta observada con prueba; presencia declarada por operador. No deducir cuenta propia de @menciones del feed ni del nombre sobreimpreso de Panda.

Auditoría técnica histórica 2026-10-26: **33 equipos × 4 apps = 132 observaciones**, TikTok/Instagram/X/Facebook instalados. Lectura TikTok: **23 feeds, 1 onboarding, 1 desconocida, 8 no comprobadas**; cero identificadores propios atribuidos, sin asumir que no haya sesión. El caso positivo de perfil propio se probó con fixtures; falta piloto real.

El 2026-10-27 se importó el reporte del usuario: **25 fichas TikTok, 19 con cuenta y 6 sin cuenta; 8 pendientes** del conjunto de 33. Son declaraciones manuales, no verificaciones actuales. Guardadas en SQLite con fecha/fuente, serial y número Panda; sin inventar @usuario. El listado y las correspondencias reales permanecen privados en `data/`. El panel tiene filtros y contadores específicos.

Lectura automática inicial de cuenta: solo TikTok ya visible; exige Perfil seleccionado + Editar perfil accionable + un único @identificador. No navega ni acepta permisos/onboarding. Otras apps: inventario técnico y confirmación manual, adaptador pendiente. Asignación no confirma sesión; coincidencia requiere observación posterior y no mayor a 24 h. La declaración del usuario persiste aparte de las lecturas.

## Rack, arranque y snapshots

Objetivo: encender servidor/rack, abrir programa y conciliar automáticamente todo lo posible. El arranque actual intenta recuperar transportes conocidos y ofrece diagnóstico, pero falta la prueba física de apagado/encendido completo.

No se identificó marca/modelo de rack/controlador/fuente. Hay fotos de chasis de 20 ranuras y anuncio genérico, sin ASIN inequívoco ni API eléctrica comprobada. No se puede inferir corriente por puerto o socket sano por ADB/LED. El operador confirmó históricamente tarjeta 10→Panda65, 17→30 y 20→51, aún sin vínculo de rack/serial verificado. La 51 recuperó imagen/Internet con indicador azul: **azul no significa avería**. No asumir extracción en caliente segura.

Snapshots 4.2 son inventario, estado lógico y archivos propios administrados. Al recuperar reponen ausentes sin sobrescribir existentes; **no** son imagen integral Android ni copia/restauración de sesiones privadas de TikTok. No prometer clonación de cuentas. Falta prueba completa tras corte y política de retención/respaldo externo.

## Última petición técnica, propuesta y límite de alcance

Después de v2.21 el usuario pidió ciclos iterativos abrir TikTok → like → scroll y modelar comentarios con mínima intervención. **Ese ciclo no se ejecutó ni se implementó después de la petición.** No existe adaptador funcional de likes/comentarios TikTok. Los documentos antiguos que dicen “pendiente de mapeo” no son prueba de disponibilidad ni autorización para ejecutar engagement coordinado.

La respuesta propuso validar el ciclo de likes/comentarios en Granjita Lab y usar TikTok para apertura, lectura y comprobaciones permitidas. Se indicó que no se ejecutaría ni perfeccionaría engagement coordinado de la granja sobre TikTok. Esto registra el alcance comunicado; no atribuye al usuario aceptación de la alternativa ni cambia el objetivo que expresó.

Arquitectura propuesta: nuestra app orquesta y persiste; Appium/UiAutomator2 verifica interfaz; Panda conserva visualización, transporte e inventario/administración documentada. Automate y una APK/agente propia son opciones para necesidades justificadas. **No existe benchmark que pruebe qué motor es más rápido**, ni un motor de comentarios con IA terminado. El modelo social más amplio es propuesta: [diseño](modelo-gestion-social.md), no esquema SQLite ya migrado.

## Prioridades abiertas al retomar trabajo técnico

1. Confirmar petición actual y releer evidencia relevante, sin lanzar acciones por el mero hecho de abrir esta guía.
2. Completar las ocho declaraciones pendientes y un piloto de perfil propio; revisar las ocho pantallas no comprobadas históricas.
3. Si se continúa el motor de interacción, acordar alcance de laboratorio y medir ejecutar → verificar logs → ajustar → repetir, con destinos propios, sin duplicar resultados inciertos.
4. Validar arranque en frío, recuperación y mapa rack/ranura/serial; identificar controlador y límites eléctricos.
5. Definir backup externo privado, retención y restauración comprobada; completar permisos de Automate solo si hace falta para la tarea.
6. IA/proveedor/credenciales y adaptadores adicionales siguen pendientes. No transformar propuestas históricas en capacidades existentes.

El [listado de pendientes](pendientes.md) conserva entradas antiguas y duplicadas. Para identidad/conteos resueltos, esta síntesis y las guías v2.20/v2.21 describen el cierre posterior; no interpretar “actual” en una entrada del 24 como estado del 28.

## Comandos de referencia y verificación

Desde la raíz, PowerShell:

```powershell
git status --short
git log -5 --oneline
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m granjita
```

El último comando **abre la aplicación y su conciliación de inicio**; no es un chequeo pasivo. Otras CLI: `scripts.panda_inventory`, `scripts.auditar_apps`, `scripts.verificar_apps`, `scripts.snapshots`, `scripts.registrar_cuentas_declaradas`. Leer guía y `--help` antes de lanzar: algunas refrescan inventario, abren sesiones o escriben registros aunque no pulsen botones Android. No repetir una importación manual solo para consultar; agrega eventos nuevos.

## Cómo mantener esta memoria

Actualizar este archivo al cambiar versión, arquitectura, decisiones, resultados materiales o siguiente bloqueo; fechar cifras y citar su guía. Mantenerlo como resumen de lectura rápida, no volcar logs ni todo el chat. Añadir detalle reproducible en docs/, avance en bitácora, tareas en pendientes y versión solo cuando cambie el programa. Conservar incertidumbres y distinguir propuesta, prueba automatizada, observación remota y reporte humano.

Revisar diff, preservar cambios ajenos, comprobar lo pertinente y sincronizar dev2026. Al preparar esta guía había cambios locales ajenos a este bloque (edición del burrito en documentación/imagen); no incluirlos accidentalmente. Esa observación es temporal: verificar Git nuevamente. Las instrucciones operativas persistentes viven en AGENTS.md, no en el historial del chat.
