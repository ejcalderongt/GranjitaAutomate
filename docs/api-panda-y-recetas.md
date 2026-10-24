# API Panda, propagación y trabajos reproducibles

Fecha: 2026-10-24.

## API comprobada

La documentación Android oficial de Some3C define WebSocket en ws://127.0.0.1:22222/ con mensajes JSON. La consulta list respondió correctamente en este equipo: 33 registros, todos con modo 2 (OTG), y onlySerial en todos. Esa identificación es independiente del identificador de transporte IP:puerto. No es la API para iPhone ni las de otros productos llamados Panda.

La documentación enumera operaciones de inventario, nombres/grupos, aplicaciones y control. La tabla de miembros indica soporte API en la versión Member; no basta el indicador visual para deducir la licencia efectiva. Aquí se comprobó la consulta real de lectura, sin cambiar la licencia ni los grupos.

Fuentes: https://doc.some3c.com/panda-manual/api-documentation y https://doc.some3c.com/panda-manual/members-and-versions.md

## Integración incluida

El botón **API Panda** consulta y compara el inventario con las fichas locales, mostrando número, nombre, serial físico, conexión y modo. No fusiona ni renombra automáticamente las fichas. La primera versión del adaptador solo envía la acción list y acepta un servidor local.

```powershell
.\.venv\Scripts\python.exe -m scripts.panda_inventory
```

El inventario completo se guarda en data/panda-inventory.json, fuera de Git. Durante la inspección Panda dejó de estar ejecutándose; se volvió a abrir y posteriormente la API respondió. Los puertos internos observados no se trataron como API sin documentación.

## Arquitectura recomendada

- GranjitaAutomate: perfiles, objetivos, cola, identidad y estadísticas.
- Panda API: inventario, transporte y operaciones administrativas documentadas, después de validar cada adaptador.
- Appium/UiAutomator2: pruebas de interfaz que requieren localizar elementos y verificar resultados.
- Automate: flujos locales y eventos cuando se hayan concedido los permisos necesarios.
- IA futura: propone parámetros o borradores dentro de un esquema; no ejecuta shell ni modifica perfiles por interpretar texto libre.

Una API puede evitar abrir sesiones de interfaz para tareas de administración y simplificar lotes. No demuestra que una interacción social sea correcta ni sustituye la verificación del resultado. No se han medido mejoras de rendimiento entre motores.

## Propagación

scripts.deploy_tools instala los cinco paquetes: Granjita Lab, UiAutomator2 server, su APK de instrumentación, Appium Settings y Automate. Automate se obtiene del APK ya instalado desde Google Play en la placa piloto. Se verifica paquete y firma de los APK fuente antes de propagar, se conservan los datos con -r y no se usan opciones de desinstalación o downgrade. Los APK se mantienen fuera de Git.

La primera pasada completa cubrió 30 fichas con identidad inequívoca. Se agregó verificación cruzada opcional: getprop actual y onlySerial de Panda deben coincidir y ser únicos en la lista de Panda. Así se pueden preparar transportes con IP reutilizada sin fusionar ni sobrescribir las asociaciones históricas locales. La pasada final completó 33 de 33 conexiones actuales; la auditoría independiente confirmó los cinco paquetes en las 33. Los registros de Panda que no están accesibles no se pueden instalar hasta que vuelvan a conectarse.

```powershell
.\.venv\Scripts\python.exe -m scripts.deploy_tools --all --workers 2 --verify-with-panda
.\.venv\Scripts\python.exe -m scripts.audit_deployment
```

La ejecución usa hasta dos instalaciones simultáneas, conserva informes anteriores y registra cada paquete por dispositivo en data/deployment-latest.json. La auditoría es independiente y de solo lectura. No habilita permisos de Automate ni copia cuentas, preferencias o datos privados entre placas. El flujo creado en la placa piloto no se clona por copiar su APK: sus flujos y permisos requieren un paso separado.

## Perfiles y recetas

profiles/laboratorio.json define el estado deseado de paquetes, motor, identidad y política de permisos. Es un perfil almacenado, no una orden para cambiar silenciosamente los ajustes Android.

recipes/lab-smoke.json define objetivo, contexto, acción tipada, parámetros y política de ejecución. La versión inicial solo permite lab_smoke en Granjita Lab, secuencialmente y sin reintentos automáticos. Valida el esquema y rechaza acciones desconocidas, shell arbitrario y rutas de perfil fuera del formato permitido.

```powershell
# Validar y previsualizar sin ejecutar
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/lab-smoke.json

# Ejecutar sobre una identidad elegida explícitamente
.\.venv\Scripts\python.exe -m scripts.run_recipe recipes/lab-smoke.json --execute --device-id ID_INTERNO
```

El objetivo y contexto se almacenan como datos; no se interpretan como instrucciones ejecutables. Las tareas conservan una copia de la receta y el perfil con SHA-256 en automation.sqlite3, para poder explicar qué se ejecutó aunque después se edite el JSON. Las plantillas sin datos privados se versionan en Git; asignaciones reales y resultados permanecen locales.

En el panel de laboratorio, **Cargar receta JSON** permite previsualizar el objetivo y cargar el comentario antes de seleccionar las placas y ejecutar. Si se modifica el comentario, se guardan los parámetros finales, no solamente el archivo original.

Validación final: 33 pruebas automatizadas con salida correcta del proceso, revisión del panel API con 33 filas, auditoría de instalación 33/33 y ejecución real de una receta local completada. Las tres asociaciones históricas de identidad siguen disponibles para revisión; la verificación cruzada de despliegue no las modificó.
