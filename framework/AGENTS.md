# Continuidad del framework

La raiz operativa es C:\dev\Framwork\framework.
El repositorio independiente esta en C:\dev\Framwork, rama dev2026-work.
El remoto es https://github.com/ejcalderongt/GranjitaAutomate.git.
La distribucion framework/ se conserva junto con la historia del repositorio.

Las carpetas anteriores bajo OneDrive y AGX-respaldo-framework son respaldos
no activos. No ejecutar el framework desde ellas ni incorporar cambios ajenos.
Cada hito autorizado y verificado debe quedar commiteado y pusheado a la rama autorizada
antes de avanzar. El traslado se publica en dev2026-work; no actualizar dev2026
sin autorizacion explicita. No usar push forzado.

Leer docs/POC_UI.md, docs/AI_TEXT_QA.md y la documentacion del repositorio padre.
Ejecutar la suite sin credenciales reales mediante scripts/run_tests.py.
Para pytest, usar PANDA_ENV_FILE apuntando a un archivo vacio temporal y
GHOST_CURSOR_AUTOCLONE=0, sin OPENAI_API_KEY heredada.

No versionar .env, proxies reales, cookies, sesiones, bases SQLite, capturas,
logs, binarios descargados ni configuraciones locales. Respaldar datos privados
por separado. No afirmar VPN operativa, interacciones logradas o sincronizacion
remota sin evidencia actual. Las ejecuciones reales requieren autorizacion.
