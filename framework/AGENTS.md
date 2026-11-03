# Continuidad del framework

Este directorio local se respalda en el repositorio
`https://github.com/ejcalderongt/GranjitaAutomate`, rama `dev2026`, bajo `framework/`.
Su Git local independiente no tiene seguimiento remoto: no asumir que hacer
cambios aquí los sincroniza automáticamente con GitHub.

El respaldo inicial se preparó en el checkout aislado hermano
`AGX-respaldo-framework/framework/`. Antes de futuros respaldos, comprobar Git,
el remoto y los cambios pendientes. Revisar y copiar únicamente archivos de
código/documentación autorizados al checkout correspondiente y sincronizar sin
push forzado. El checkout histórico `AGX` puede tener cambios pendientes ajenos:
no incorporarlos ni sobrescribirlos por accidente.

Leer `docs/POC_UI.md`, `docs/AI_TEXT_QA.md` y, en el repositorio padre,
`docs/framework-qa-2026-11-02.md`. Ejecutar `python scripts/run_tests.py` para
pruebas herméticas; no heredar credenciales reales en tests.

No versionar `.env`, proxies reales, cookies, sesiones, bases SQLite, capturas,
logs, binarios descargados ni datos privados. Las bases necesitan respaldo
privado separado. No afirmar VPN operativa, interacción social lograda ni
sincronización remota sin evidencia actual.
