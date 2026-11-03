# Smoke test de proxy móvil

`config/proxies.py` añade ProxyManager sin reemplazar ADB, el pool ni sus
reservas. Su método async `ejecutar_ciclo_rotacion_segura` devuelve una IP
pública normalizada; `rotar_ip_movil` es el método equivalente. No se acredita
reputación de la IP, tipo de operador 4G/5G ni aislamiento del sistema operativo.

## Configuración privada

Completar tiktok_warmer/.env sin sobrescribir la clave OpenAI del proyecto:

- PROXY_HOST y PROXY_PORT: endpoint real del proveedor.
- PROXY_PROTOCOL: http, https o socks5. Si falta, se usa el esquema de
  PROXY_URL; si tampoco existe, http. No confundir HTTP con HTTPS del destino.
- PROXY_USER y PROXY_PASS: par de credenciales. Si cualquiera está definido,
  ambos deben estar completos. Si no, se aceptan PROXY_USERNAME/PROXY_PASSWORD.
- PROXY_ROTATION_URL: enlace real y secreto que el proveedor documente para GET.
- PROXY_ROTATION_WAIT_SECONDS: pausa determinista entre 0 y 30; predeterminado 10.
- PROXY_ROTATION_ALLOW_LOCAL_HTTP=1 permite HTTP únicamente hacia una IP
  privada o localhost. Por defecto el control requiere HTTPS.

Orden de prioridad por clave: entorno del proceso, .env del laboratorio,
.env raíz. Un env_path explícito permite otra ubicación. El soporte SOCKS5
requiere httpx[socks], ya declarado en las dependencias. No se imprime la URL
de rotación ni el cuerpo del proveedor. No hay credenciales en argumentos CLI.

## Secuencia y límites

1. Registrar el inicio del intento en SQLite antes de emitir tráfico.
2. Buscar la última referencia de IP validada para cuenta y endpoint. Si no
   existe, medir una línea base HTTPS a través del proxy antes de la rotación.
3. Emitir un único GET de control, directo y sin heredar proxies del entorno.
   No se siguen redirecciones ni se reintenta automáticamente un webhook.
4. Rechazar estados HTTP no exitosos o un error estructurado del proveedor.
   Un 2xx solo acredita recepción de la solicitud.
5. Esperar el plazo determinista cancelable; no simula interés humano.
6. Consultar https://api.ipify.org?format=json mediante el proxy autenticado,
   usando httpx.AsyncClient y TLS validado. No hay fallback a conexión directa.
7. Rechazar IP inválida/no pública, timeout o una salida igual a la referencia
   anterior. Solo entonces devolver la nueva IP al orquestador.
8. Abrir Patchright con esas mismas credenciales y verificar de nuevo la IP
   dentro del navegador. Una discrepancia impide navegar a TikTok.

Cada llamada HTTP tiene un presupuesto de 10 segundos; el límite de 30 s es
para la pausa, no para toda la transacción. asyncio.Event se atiende directamente
y señales de hilo se consultan cada 50 ms. La cancelación cancela la petición
en curso y se propaga al cierre protegido de la POC. Una petición cancelada o
con timeout puede haberse aplicado en el proveedor: nunca se repite a ciegas.

## UI

```powershell
.\.venv\Scripts\python.exe -m ui.poc_dashboard
```

La opción Smoke móvil está activada inicialmente. Inicio ejecuta el preflight
antes de crear el contexto; un fallo deja el panel recuperable con estado de
fallo y sus eventos guardados. Desactivar la opción selecciona explícitamente
el laboratorio anterior sin rotación; no se presenta como un smoke móvil.
El API POCSettings conserva rotate_mobile=False para compatibilidad con los
llamadores previos; el panel le pasa explícitamente el estado del control.

La rotación solo se incorpora a esta POC de una cuenta, protegida por farm.lock.
No se lanza una orden de rotación por cada placa del clúster; cambiar un módem
compartido podría afectar a otras sesiones. Sesiones, sandbox, TLS, el puente
dinámico y los límites de ciclos continúan bajo los controles existentes.

## Auditoría

La tabla eventos_red_qa del archivo sessions/telemetry_qa.db conserva:

- UTC, run_id, account_id y operation_id para correlacionar un intento.
- accion/fase/estado y el nombre legible del evento.
- latencia_ms de la solicitud y latencia_total_ms de la operación completa.
- HTTP status, cambio_ip y códigos controlados de error.
- Referencias hash del endpoint y de las IP; no se guardan sus valores en claro.

Los eventos de validación incluyen Conexión Segura Establecida y Fallo de
Validación de Red. El primero se refiere a la petición HTTPS por proxy de esa
fase; no acredita una VPN. Rotación Verificada requiere una diferencia observada
respecto a la última validación. En un endpoint que cambia por cada petición,
la diferencia no demuestra causalidad del webhook ni estabilidad de sesión.
La comprobación del navegador detecta una salida inesperada y detiene el arranque.

Si SQLite no permite registrar el intento, no se envía el control de rotación.
Si falla su auditoría posterior no se habilita el navegador. Los clientes HTTP
propios se cierran; clientes inyectados permanecen bajo propiedad del llamador.

```sql
SELECT timestamp_utc, accion, fase, evento, estado, latencia_ms, latencia_total_ms,
       http_status, cambio_ip, error_codigo
FROM eventos_red_qa ORDER BY id DESC LIMIT 30;
```

Comprobación de esta entrega: las variables antiguas de usuario/contraseña
existen localmente y el protocolo resuelto es SOCKS5. PROXY_ROTATION_URL no se
encontró en la configuración resuelta. No se ejecutó una rotación real ni se
certificó que el endpoint actual corresponda a un producto móvil. Las pruebas
de red usan transportes HTTP simulados y SQLite temporal, separados de producción.

Referencia HTTPX: https://www.python-httpx.org/async/ y
https://www.python-httpx.org/advanced/proxies/
