# Instalación del modo web en otra PC

Copiar el código del proyecto con `requirements.txt`, `requirements-web.txt`,
`scripts/` y `config/web_selectors.mobile.json`. No copiar `.venv`: se crea en el
destino. Instalar Python 3.11 o superior y ejecutar desde la raíz:

```powershell
python scripts/preparar_web.py --install
```

El script crea `.venv` si falta, instala las dependencias generales y
`patchright==1.64.3`, y descarga Chromium. Requiere acceso a Internet.
Para comprobar la instalación:

```powershell
.\.venv\Scripts\python.exe scripts/preparar_web.py
.\.venv\Scripts\python.exe scripts/run_tests.py
```

Crear `.env` localmente con `OPENAI_API_KEY`, manteniendo las restricciones de
acceso del usuario del servidor. No incluir claves, cookies, bases de datos ni
contraseñas de proxy en Git. Las exclusiones del proyecto cubren `.env`,
`sessions/`, `logs/`, `data/` y la configuración local de proxies.

Configurar `config/proxy_pool.json` mediante el panel de proxies. En otra PC,
cambiar la dirección de entrada por la del servidor proxy correspondiente y
verificar la IP de salida real. `192.168.1.199` pertenece al laboratorio actual;
no es una dirección universal. Para ejecutar también proxy.py localmente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-laboratory.txt
```

Consultar la configuración del proxy local y sus permisos de firewall en el
README; instalar la dependencia no configura ni arranca por sí solo el servicio.

## Operación desde Streamlit

```powershell
.\.venv\Scripts\python.exe main.py --ui
```

En Panel de Control → Automatización web · Patchright:

1. Seleccionar un proxy habilitado. Si requiere autenticación, completar usuario
   y contraseña. Se transmiten al proceso por variables de entorno; no se escriben
   en la línea de comandos ni en el JSON del trabajo.
2. Mantener el perfil `cuenta_tiktok_01` para reutilizar
   `sessions/cuenta_tiktok_01`. Su cuenta de ejecución conserva el vínculo SQLite
   del endpoint si ya existe. No abrir ese perfil en dos navegadores simultáneos.
3. Pulsar Abrir sesión web, completar el acceso manual y cerrar la ventana.
4. Validar los selectores de `config/web_selectors.mobile.json` contra la versión
   web usada. Son candidatos, no una certificación de compatibilidad con TikTok.
5. Marcar la verificación manual de sesión y pulsar Iniciar navegación web.
   La casilla de interacción está desactivada por defecto: sin marcarla, se
   consulta la IA y se avanza el feed, pero no se publican likes/comentarios.

El proceso abre `/foryou`, observa el DOM 10–25 segundos y extrae `video-desc`
del contenedor activo. Usa el cliente existente `gpt-4o-mini`, su validación JSON
y los límites globales. En modo de interacción, el comentario se escribe carácter
por carácter y se envía con Enter. Ese evento no confirma aceptación por TikTok.
Los fallos se auditan y se aíslan del proceso Streamlit y de otras cuentas.

La UI web controla un navegador en Windows; el control de las placas físicas
permanece en los modos Android. Las comprobaciones de salida y los leases SQLite
son compartidos para evitar uso concurrente del mismo endpoint.

## Adaptador de cursor pendiente

`playwright_ghost_cursor` no está disponible en el entorno de referencia. No se
incluye una dependencia con nombre supuesto. El adaptador admite un paquete
Python que exponga `create_cursor(page).move_to(x, y)` síncrono. Hasta confirmar
su origen y versión, el panel muestra que usa el método estándar. El repositorio
previamente indicado `m1guelpf/playwright-ghost-cursor` respondió Repository not
found. No se declara que GhostCursor esté instalado ni validado.

Las funciones públicas son `simular_movimiento_tactil_humano` y
`hacer_swipe_feed_tiktok`. La primera efectúa un único click después del
posicionamiento opcional; la segunda conserva la captura `post_swipe` y la
liberación del botón en `finally`.

## Compatibilidad con el fragmento de integración

También se exportan `simular_entrada_tactil(page, selector=None)` y
`ejecutar_swipe_feed(page, account_id='cuenta')`. Las acciones conservan el
registro visual y la regla de no repetir un click con resultado incierto. Si
falla únicamente el posicionamiento opcional del cursor, se ejecuta un único
click estándar. Un control no visible devuelve `False` sin tocarlo.

El preparador acepta `--cursor-source` junto con `--install` cuando se disponga
de una URL Git HTTPS completa de un paquete Python compatible. Preferir una
revisión fija para repetir la instalación en otra PC. `git+https://github.com`
se rechaza antes de instalar: no identifica un repositorio. No se reemplaza por
una fuente inventada. La instalación opcional tiene un timeout de 120 segundos
y una comprobación de importación de 15 segundos; su fallo conserva el modo
estándar. Este timeout es independiente del clonador de acciones (15 segundos).

El fragmento original se adapta a procesos aislados y señal de parada propia.
No se usa `st.session_state` dentro del worker ni se guarda un objeto Page en
Streamlit. Abrir sesión no consulta OpenAI. Las decisiones siguen el esquema
JSON validado existente y las acciones requieren la casilla explícita del panel;
no se interpreta texto libre buscando «sí». No se añade python-dotenv: el
cargador del proyecto ya lee únicamente las variables autorizadas sin expandirlas.

El preparador informa disponibilidad de componentes, no «listo para producción»:
la aceptación de un comentario, la autenticación real y los selectores de la
versión instalada deben verificarse en la sesión de laboratorio.
