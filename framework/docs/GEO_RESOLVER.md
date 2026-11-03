# GeoIP asíncrono con fallback

`core/geo_resolver.py` expone
`await obtener_geolocalizacion_con_bypass(ip_objetivo, cliente_http=None)`.
Es redundancia entre proveedores, no un mecanismo para ignorar cuotas.
Cada proveedor recibe como máximo una consulta por resolución.

Orden y endpoints:

1. `https://ipapi.co/<ip>/json/`
2. `http://ip-api.com/json/<ip>?fields=status,message,query,countryCode,continentCode,org,isp`
3. `https://ipinfo.io/<ip>/json`

Se consulta la IP observada por Chromium y se valida que la IP devuelta
coincida. La función normaliza pais, continente, org y provider_used, además
de estado, transporte e histórico de intentos. Rechaza IPs privadas, payloads
incompletos y errores internos. Tolera 429, otros estados HTTP, timeouts,
errores de transporte y JSON inválido. Cada intento tiene un límite asíncrono
de 10 segundos; la cancelación se propaga. No se guardan excepciones crudas.
Un cliente prestado no se cierra; uno creado localmente sí.

## Integración

Patchright síncrono ya tiene un loop activo. `resolver_geo_en_worker` programa
la coroutine en el loop del puente local, sin anidar asyncio.run en el hilo
del navegador. Para HTTP sin puente usa un worker separado con loop propio.
El AsyncClient se crea y cierra en el mismo loop, con proxy explícito y
trust_env=False. Sin cliente inyectado, la API del resolver permite consulta
directa; el diagnóstico siempre inyecta un cliente con proxy.
No se cambia TLS, sandbox, credenciales ni el cierre defensivo en finally.

```powershell
.\.venv\Scripts\python.exe -m pip install -r tiktok_warmer/requirements.txt
.\.venv\Scripts\python.exe tiktok_warmer/test_connection.py --headless
```

Los reportes nuevos permanecen en runs/proxy-preflight-<run_id>/resultado.json.
No se sobrescriben informes secure-context anteriores. Se registran:

- proxy_verified: éxito del HTTPS observado en Chromium.
- geo_provider_used, geo_fallback_used, geo_attempts y geo_transport.
- detected_continent, country_code, geo_status y region_verified.
- cleanup_confirmed: cierre de contexto, runtime y puente sin errores.

Si fallan todos los proveedores: status partial, error_code geo_unavailable,
continente UNKNOWN y region_verified false; proxy_verified conserva su éxito.
Si se obtiene otro continente: status region_mismatch. No se consultan más
proveedores después de una respuesta válida para buscar una clasificación
favorable. Salida 0 requiere preflight completo; salida 2 indica incompleto.

Europa no equivale a Unión Europea. Para ipinfo sin continente se usa una
lista ampliada (incluidos GB, CH y NO). Países transcontinentales requieren
una clasificación de continente explícita del proveedor, no una suposición.

## Evidencia y límites

GeoIP es una clasificación del proveedor, no certificación física.
ip-api gratuito usa HTTP sin TLS y limita uso; el informe conserva ese
transporte. Su plan gratuito no autoriza uso comercial: para ese uso se
requiere un plan adecuado o proveedor alternativo. IPinfo puede requerir
token o aplicar límites; no se garantiza disponibilidad gratuita.

Prueba real: 185.244.21.214; ipapi.co 429; ip-api.com 200, continente EU,
país RU; cleanup_confirmed true. Observación puntual de una salida rotativa.

Fuentes oficiales:
- https://ipapi.co/api/
- https://ip-api.com/docs/api:json
- https://ipinfo.io/developers/core-api
