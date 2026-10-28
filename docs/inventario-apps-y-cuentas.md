# Apps y cuentas · v2.21

## Uso

Abrir **Apps y cuentas** en el paso 3 de la pantalla principal. También puede ejecutarse `python -m granjita.app_inventory_ui` con el entorno del proyecto.

1. Elegir TikTok, Instagram, X o Facebook y marcar dispositivos.
2. **Actualizar inventario** consulta instalación, variantes, versión y primer plano de las cuatro apps. Una consulta fallida queda sin comprobar, nunca como app ausente.
3. **Leer pantalla** analiza TikTok que ya esté visible, sin abrirlo ni navegar. Para intentar identificar cuenta propia, dejar visible Perfil; se requieren pestaña seleccionada, control Editar perfil y un único identificador público. Un feed o una mención no prueba cuenta propia. Otras apps admiten confirmación manual; su adaptador automático está pendiente.
4. La cuenta esperada es una asignación, separada de la cuenta observada. La confirmación manual de sesión exige identificador visible. Una coincidencia exige evidencia posterior a la asignación, no mayor a 24 horas; no asegura que la sesión siga vigente.
5. **Ver historial** muestra las últimas 200 observaciones y 100 asignaciones; SQLite conserva todas. La vista actual consulta cada fuente independientemente de esos límites.

## Declaración de presencia de cuenta

El listado del usuario se guarda como **Con cuenta · declarado** o **Sin cuenta · declarado**, con fecha, fuente `user_report`, número Panda como referencia e identidad física/canónica como vínculo persistente. No inventa identificadores, no prueba sesión actual ni equivale a cuenta asignada. Las lecturas técnicas o de pantalla posteriores no borran esa declaración. Los filtros y el resumen permiten ver con cuenta, sin cuenta y pendientes de declarar.

El 2026-10-27 se registraron 25 declaraciones: **19 con cuenta y 6 sin cuenta**. Los otros **8 de los 33 equipos** quedaron pendientes. Se resolvió cada número mediante la API local de Panda y su serial físico, exigiendo una única ficha. Los datos de correspondencia y el listado real permanecen en `data/`, fuera de Git. La captura proporcionada es referencia; no se atribuyeron cuentas desde los nombres sobreimpresos en Panda.

Importador reproducible, con archivo JSON privado de formato `{ "2": true, "3": false }` (ejemplo ficticio):

```powershell
.\.venv\Scripts\python.exe -m scripts.registrar_cuentas_declaradas data/listado-privado.json
.\.venv\Scripts\python.exe -m scripts.registrar_cuentas_declaradas data/listado-privado.json --apply
```

La primera orden valida sin escribir declaraciones. La segunda respalda SQLite antes de agregar el lote en una transacción; cualquier identidad ambigua rechaza el lote completo. Repetir la aplicación agrega otro evento histórico; no elimina el anterior. La importación no cambia números de Panda, cuentas ni teléfonos.

## Validaciones y límites

Auditoría técnica inicial: 33 equipos y 132 observaciones, las cuatro apps instaladas. Lectura inicial de TikTok: 23 feeds, una configuración pendiente, una pantalla desconocida y ocho no comprobadas; cero identificadores propios atribuidos. Son referencias históricas del 2026-10-26, no estado actual. El caso positivo de perfil propio se validó con fixtures; falta un piloto real mostrando ese perfil. Tener app abierta no prueba cuenta.

Para repetir la auditoría explícitamente: `python -m scripts.auditar_apps --all`; pantalla: agregar `--screen --app tiktok`. Se bloquea si hay tareas activas. No se hacen likes, login, elecciones de datos personales ni aceptación de diálogos.

SQLite esquema 7 agrega `device_app_observations` y `device_app_assignments`, conservando identidades y snapshots previos y respaldo anterior a la migración. Las declaraciones usan alcance `declaration`, separado de `technical` y `screen`. Integridad comprobada tras importar. No se guardan XML crudos, contraseñas, cookies, tokens ni capturas; solo estados, versión, fecha, fuente, señales y hash de pantalla. Identificadores públicos y correspondencias reales permanecen privados en SQLite local. Git respalda código/documentación, no esta base; se necesita política de respaldo externo privado.

Validación automatizada: 131 pruebas, incluyendo separación de fuentes, atomicidad, identidad ambigua, historial y controles de lectura sin navegación.
