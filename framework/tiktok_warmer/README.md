# Diagnostico de proxy y navegador

Desde `C:\dev\Framwork\framework`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tiktok_warmer/requirements.txt
.\.venv\Scripts\python.exe -m patchright install chromium
notepad tiktok_warmer/.env
.\.venv\Scripts\python.exe tiktok_warmer/test_connection.py
```

En `tiktok_warmer/.env`, completar `PROXY_URL=http://host:puerto`,
`PROXY_USERNAME` y `PROXY_PASSWORD` con los datos de conexion del panel.
El dominio comercial `http://proxy-cheap.com` no es un endpoint valido.
El archivo local preparado conserva esa linea solicitada y anade
`PROXY_HOST=thehub.proxy-cheap.com` y `PROXY_PORT=8080`. Cuando estan definidos,
estos dos campos sustituyen el host y puerto de PROXY_URL conservando su esquema.
Sustituir `MI_CONTRASENA_REAL` en PROXY_PASSWORD; el diagnostico rechaza ese
marcador antes de abrir el navegador. El usuario ya esta configurado localmente.
Para proxies autorizados por IP, dejar usuario y contrasena vacios.
Las credenciales son las del proxy, no la contrasena de la cuenta del proveedor.
Tambien se aceptan credenciales URL codificadas, pero se recomiendan los campos
separados para evitar errores con caracteres especiales.

La configuracion se lee, en orden de prioridad: variables del proceso,
`.env` de esta carpeta, `.env` del framework. Ninguna clave OpenAI se sustituye;
no se llama a OpenAI en el diagnostico. Los archivos `.env` y `sessions/`
estan excluidos por las reglas existentes de Git.

`--headless` permite ejecucion sin ventana. `--check-tiktok` anade unicamente
una navegacion de lectura; no inicia sesion, publica ni interactua. Una
respuesta HTTP no certifica ausencia de desafios. El contexto es Chromium
movil Pixel 5 con viewport 390x844 y soporte tactil. No se afirma que sea
Safari de iPhone ni indetectable.

El diagnostico abre HTTPS por el contexto configurado con proxy, lee una IP
valida desde api.ipify.org y consulta esa misma IP con fallback asincrono
ipapi.co  ip-api.com  ipinfo.io. Europa se
verifica con `continent_code == EU`, diferente de pertenecer a la Union
Europea. La geolocalizacion es informacion del proveedor, no una garantia
contractual. No se prueba el aislamiento Android ni posibles fugas de otros
protocolos. No hay fallback a conexion directa.

Cada ejecucion escribe `runs/proxy-preflight-<id>/resultado.json` en el
framework principal. Conserva etapas, IP, region, estado de autenticacion,
errores clasificados y limpieza. No incluye usuario, contrasena ni textos de
excepcion que podrian contener secretos. Salida 0 significa preflight
completo; salida 2 indica fallo o region no confirmada.

Referencias:
- https://support.proxy-cheap.com/hc/en-us/articles/38182068823837-Proxy-Cheap-Frequently-Asked-Questions
- https://ipapi.co/api/

## SOCKS5 autenticado en Chromium

La configuracion local usa `PROXY_URL=socks5://thehub.proxy-cheap.com:8080`.
Conservar PROXY_HOST/PROXY_PORT y las credenciales del archivo privado.
Se aceptan tambien los alias PROXY_USER y PROXY_PASS, con prioridad de
PROXY_USERNAME y PROXY_PASSWORD si estan definidos.

Chromium no admite autenticacion SOCKS5 con los campos username/password de
Playwright. `core/socks_bridge.py` inicia un listener HTTP unicamente en
127.0.0.1, con puerto dinamico, y usa pproxy 2.7.9 para autenticar hacia el
servidor SOCKS5. Las credenciales permanecen en memoria, sin argumentos de
subproceso ni URI registrada. No se configura una ruta alternativa directa.
El listener es de uso local: cualquier proceso local que conozca el puerto
puede usarlo durante la sesion. No exponerlo a la LAN.

`playwright.stop()` cierra tambien el puente y cancela sus tareas. Ante fallo
de arranque se limpian ambos recursos. El adaptador tambien esta integrado
en el `core/browser.py` del framework; los proxies web pueden declarar
server socks5://host:puerto y username/password en su configuracion privada.

El main.py existente conserva su orquestacion de cuentas, reservas, auditoria,
opcion de login manual y limites de ciclos. No se reemplaza por un bucle
infinito. La integracion no deshabilita TLS ni el sandbox, ni ejecuta likes
o comentarios durante el diagnostico. Un clic o Enter no acredita que el
servidor haya aceptado una interaccion.

Prueba local automatizada: CONNECT HTTP al puente, autenticacion SOCKS5
contra servidor de prueba, transferencia bidireccional y cierre del listener.
La comprobacion real sigue dependiendo de la disponibilidad del proveedor;
429 de geolocalizacion o timeout se registran como fallo, sin certificar region.

Referencia de API del puente: https://github.com/qwj/python-proxy#server-api
Referencia del navegador: https://playwright.dev/docs/network

El resolver GeoIP, los estados parciales y los limites de los proveedores
estan documentados en ../docs/GEO_RESOLVER.md. GeoIP no disponible no cambia
proxy_verified a false; la region permanece desconocida hasta acreditarse.

## API del core y ciclo de vida

`core.browser.iniciar_contexto_seguro(account_id)` abre Patchright con el
proxy del entorno y un puente propio de puerto dinamico. La prioridad es:
variables del proceso, tiktok_warmer/.env, .env raiz. Admite `proxy=...` para
una asignacion explicita del pool: esa asignacion tiene prioridad sobre el
entorno y conserva las reservas por cuenta del orquestador.

`puerto_puente_local=<entero>` selecciona unicamente un listener externo en
127.0.0.1; no intenta autenticar SOCKS5 desde Chromium ni crea un segundo
puente. El llamador conserva la responsabilidad de cerrar ese listener externo.
No existe un puerto 8081 predeterminado.

El retorno sigue siendo `(playwright, context, page)`.
Usar `cerrar_contexto_seguro(context, playwright)` en finally: intenta ambos
cierres por separado y devuelve False si alguno falla. El worker llamado
desde main.py ya usa esta rutina; una limpieza no confirmada conserva la
cuarentena/reserva segun las reglas del supervisor.

No se cambian los flags del main.py: --web-accounts selecciona perfiles,
--web-engine patchright usa este adaptador, --web-login-only permite login
manual y --cycles limita la ejecucion. El diagnostico no ejecuta acciones
sociales. El perfil Pixel 5 proviene del catalogo del navegador instalado,
sin fijar un User-Agent obsoleto ni anadir --no-sandbox.
