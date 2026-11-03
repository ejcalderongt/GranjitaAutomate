# Proxy-Cheap residencial rotativo SOCKS5

La modalidad del panel es Rotating Residential / Random IP, no un módem móvil
con API de rotación. Las credenciales privadas están en tiktok_warmer/.env;
no se incorporan al código, al ejemplo de configuración ni a SQLite.

Configuración pública aplicada:

```dotenv
PROXY_PROVIDER=proxy_cheap
PROXY_MODE=rotating_residential
PROXY_PROTOCOL=socks5
PROXY_HOST=thehub.proxy-cheap.com
PROXY_PORT=8080
```

PROXY_USER/PROXY_PASS y los alias anteriores se guardan únicamente en el
archivo privado, que conserva ACL y exclusión de Git. No se cambia la clave
OpenAI raíz. Para este perfil, una configuración HTTP explícita genera
proxy_cheap_requires_socks5: no se intenta HTTP como alternativa.

## Flujo

`await ProxyManager(...).preparar_conexion(stop)` valida HTTPS a través del
proxy autenticado y devuelve la IP. La entrada anterior
ejecutar_ciclo_rotacion_segura delega en esta política para compatibilidad.
No se exige PROXY_ROTATION_URL, no se llama a un webhook y no se aplica la
pausa de reconexión de módem. Incluso una llamada antigua a rotar_ip_movil
se delega al preflight residencial cuando PROXY_MODE=rotating_residential:
no valida PROXY_ROTATION_URL ni emite solicitudes de control. El webhook
solo pertenece al modo mobile_api explícito.

La igualdad entre dos IP observadas no se considera fallo de conectividad:
Random IP puede reasignar salidas, pero no garantiza unicidad en cada consulta.
Una IP distinta en el navegador también es admisible en esta modalidad. Se
exige una IP pública válida y una respuesta HTTPS válida; errores de proxy
siguen bloqueando el inicio. No se declara una rotación forzada ni cambio
confirmado de módem en los eventos residenciales.

Chromium usa el puente HTTP local → SOCKS5 autenticado ya integrado. Su listener
HTTP es de loopback; la conexión al proveedor sigue siendo SOCKS5. No se envían
usuario/contraseña SOCKS5 directamente a Chromium. El sandbox, TLS y los cierres
defensivos permanecen activos.

El control del panel ahora dice Validar red según PROXY_MODE del .env. Se
mantiene activado y selecciona automáticamente esta ruta residencial desde
el archivo; no obliga a proporcionar una API móvil inexistente.

```powershell
.\.venv\Scripts\python.exe -m ui.poc_dashboard
```

eventos_red_qa añade la columna modo para distinguir mobile_api de
rotating_residential. Guarda intentos, latencias, estados y referencias hash;
no almacena las credenciales ni la URL de control. Los registros anteriores se
preservan con su modalidad móvil previa.

La selección Región del hostname Europa no acredita por sí sola continente
EU para una salida con País Aleatorio. La verificación GeoIP de la IP observada
en Chromium sigue activa si el operador exige Europa. Para una IP estable
durante login, el proveedor ofrece Session IP: debe copiarse su configuración
generada desde el panel, sin inventar sufijos ni alterar credenciales al azar.

## Comprobación real

Reporte: runs/residential-ca3ff51925ae43718bcafabb8ec806db/resultado.json.
Consulta por SOCKS5: 71.84.3.245. Chromium: HTTP 200 e IP 83.56.220.150.
Cierre confirmado. Son observaciones puntuales de conexiones distintas; no
se consultó TikTok, OpenAI ni una URL de rotación. Los reportes de diagnóstico
incluyen IPs observadas; la tabla de QA conserva referencias hash.

Fuente oficial de la modalidad Random/Session:
https://support.proxy-cheap.com/hc/en-us/articles/30423207064349-How-to-use-residential-rotating-proxies-Step-by-Step-Tutorial
