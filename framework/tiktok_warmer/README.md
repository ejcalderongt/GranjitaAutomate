# Diagnóstico de proxy y navegador

Desde `C:\Users\labor\OneDrive\Documents\ChatGPT\Framwork`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tiktok_warmer/requirements.txt
.\.venv\Scripts\python.exe -m patchright install chromium
notepad tiktok_warmer/.env
.\.venv\Scripts\python.exe tiktok_warmer/test_connection.py
```

En `tiktok_warmer/.env`, completar `PROXY_URL=http://host:puerto`,
`PROXY_USERNAME` y `PROXY_PASSWORD` con los datos de conexión del panel.
El dominio comercial `http://proxy-cheap.com` no es un endpoint válido.
El archivo local preparado conserva esa línea solicitada y añade
`PROXY_HOST=thehub.proxy-cheap.com` y `PROXY_PORT=8080`. Cuando están definidos,
estos dos campos sustituyen el host y puerto de PROXY_URL conservando su esquema.
Sustituir `MI_CONTRASENA_REAL` en PROXY_PASSWORD; el diagnóstico rechaza ese
marcador antes de abrir el navegador. El usuario ya está configurado localmente.
Para proxies autorizados por IP, dejar usuario y contraseña vacíos.
Las credenciales son las del proxy, no la contraseña de la cuenta del proveedor.
También se aceptan credenciales URL codificadas, pero se recomiendan los campos
separados para evitar errores con caracteres especiales.

La configuración se lee, en orden de prioridad: variables del proceso,
`.env` de esta carpeta, `.env` del framework. Ninguna clave OpenAI se sustituye;
no se llama a OpenAI en el diagnóstico. Los archivos `.env` y `sessions/`
están excluidos por las reglas existentes de Git.

`--headless` permite ejecución sin ventana. `--check-tiktok` añade únicamente
una navegación de lectura; no inicia sesión, publica ni interactúa. Una
respuesta HTTP no certifica ausencia de desafíos. El contexto es Chromium
móvil Pixel 5 con viewport 390x844 y soporte táctil. No se afirma que sea
Safari de iPhone ni indetectable.

El diagnóstico abre HTTPS por el contexto configurado con proxy, lee una IP
válida desde api.ipify.org y consulta esa misma IP con fallback asíncrono
ipapi.co → ip-api.com → ipinfo.io. Europa se
verifica con `continent_code == EU`, diferente de pertenecer a la Unión
Europea. La geolocalización es información del proveedor, no una garantía
contractual. No se prueba el aislamiento Android ni posibles fugas de otros
protocolos. No hay fallback a conexión directa.

Cada ejecución escribe `runs/proxy-preflight-<id>/resultado.json` en el
framework principal. Conserva etapas, IP, región, estado de autenticación,
errores clasificados y limpieza. No incluye usuario, contraseña ni textos de
excepción que podrían contener secretos. Salida 0 significa preflight
completo; salida 2 indica fallo o región no confirmada.

Referencias:
- https://support.proxy-cheap.com/hc/en-us/articles/38182068823837-Proxy-Cheap-Frequently-Asked-Questions
- https://ipapi.co/api/

## SOCKS5 autenticado en Chromium

La configuración local usa `PROXY_URL=socks5://thehub.proxy-cheap.com:8080`.
Conservar PROXY_HOST/PROXY_PORT y las credenciales del archivo privado.
Se aceptan también los alias PROXY_USER y PROXY_PASS, con prioridad de
PROXY_USERNAME y PROXY_PASSWORD si están definidos.

Chromium no admite autenticación SOCKS5 con los campos username/password de
Playwright. `core/socks_bridge.py` inicia un listener HTTP únicamente en
127.0.0.1, con puerto dinámico, y usa pproxy 2.7.9 para autenticar hacia el
servidor SOCKS5. Las credenciales permanecen en memoria, sin argumentos de
subproceso ni URI registrada. No se configura una ruta alternativa directa.
El listener es de uso local: cualquier proceso local que conozca el puerto
puede usarlo durante la sesión. No exponerlo a la LAN.

`playwright.stop()` cierra también el puente y cancela sus tareas. Ante fallo
de arranque se limpian ambos recursos. El adaptador también está integrado
en el `core/browser.py` del framework; los proxies web pueden declarar
server socks5://host:puerto y username/password en su configuración privada.

El main.py existente conserva su orquestación de cuentas, reservas, auditoría,
opción de login manual y límites de ciclos. No se reemplaza por un bucle
infinito. La integración no deshabilita TLS ni el sandbox, ni ejecuta likes
o comentarios durante el diagnóstico. Un clic o Enter no acredita que el
servidor haya aceptado una interacción.

Prueba local automatizada: CONNECT HTTP al puente, autenticación SOCKS5
contra servidor de prueba, transferencia bidireccional y cierre del listener.
La comprobación real sigue dependiendo de la disponibilidad del proveedor;
429 de geolocalización o timeout se registran como fallo, sin certificar región.

Referencia de API del puente: https://github.com/qwj/python-proxy#server-api
Referencia del navegador: https://playwright.dev/docs/network

El resolver GeoIP, los estados parciales y los límites de los proveedores
están documentados en ../docs/GEO_RESOLVER.md. GeoIP no disponible no cambia
proxy_verified a false; la región permanece desconocida hasta acreditarse.

## API del core y ciclo de vida

`core.browser.iniciar_contexto_seguro(account_id)` abre Patchright con el
proxy del entorno y un puente propio de puerto dinámico. La prioridad es:
variables del proceso, tiktok_warmer/.env, .env raíz. Admite `proxy=...` para
una asignación explícita del pool: esa asignación tiene prioridad sobre el
entorno y conserva las reservas por cuenta del orquestador.

`puerto_puente_local=<entero>` selecciona únicamente un listener externo en
127.0.0.1; no intenta autenticar SOCKS5 desde Chromium ni crea un segundo
puente. El llamador conserva la responsabilidad de cerrar ese listener externo.
No existe un puerto 8081 predeterminado.

El retorno sigue siendo `(playwright, context, page)`.
Usar `cerrar_contexto_seguro(context, playwright)` en finally: intenta ambos
cierres por separado y devuelve False si alguno falla. El worker llamado
desde main.py ya usa esta rutina; una limpieza no confirmada conserva la
cuarentena/reserva según las reglas del supervisor.

No se cambian los flags del main.py: --web-accounts selecciona perfiles,
--web-engine patchright usa este adaptador, --web-login-only permite login
manual y --cycles limita la ejecución. El diagnóstico no ejecuta acciones
sociales. El perfil Pixel 5 proviene del catálogo del navegador instalado,
sin fijar un User-Agent obsoleto ni añadir --no-sandbox.
