# Control de un helper VPN sin root

El módulo `core/network_lockdown.py` configura un helper **existente y funcional**.
Las fuentes de control están en `android/agx_vpn_helper/`. El compilador genera
`tools/agx_vpn_helper.apk`, pero esta versión declara `control_plane_only`:
**no incluye un stack TCP de usuario ni acredita un túnel navegable**. Rechaza
crear una TUN si falta `org.agx.vpntunnel.transport.HttpConnectTcpEngine`, que debe
implementar `PacketEngine`. No se entrega un bucle que descarte todos los datos
como si fuera un convertidor TUN-a-HTTP funcional.

## Operación

En el panel seleccionar «VPN Always-on + Lockdown · requiere helper y USB», o usar:

```powershell
.\.venv\Scripts\python.exe main.py --smoke-test 3 --cycles 1 --network-mode vpn-lockdown
```

El primer ensayo requiere rutas ADB USB directas: las rutas Panda TCP podrían
perderse al bloquear el tráfico fuera de VPN, impidiendo restaurar la placa.
No se habilita Lockdown sobre el único canal de gestión TCP.

Si el paquete no existe, instalar el APK local y confirmar `pm path`. Un APK
instalado no implica autorización de VPN. `VpnService.prepare()` requiere
consentimiento del usuario cuando corresponda. Android permite gestionar Always-on
mediante DevicePolicyManager a un Device Owner/Profile Owner autorizado. Escribir
claves secure no garantiza que el framework haya activado la política ni el túnel.
No se conceden permisos ni se configura Device Owner automáticamente.

## Contrato exigido al APK propietario

- Paquete: `org.agx.vpntunnel` y servicio `.VpnConfigService`, protegido por
  BIND_VPN_SERVICE. El control ADB pasa por `.ControlReceiver`, protegido por DUMP,
  con extra `operation=start/stop`. Recibe extras `host` y
  `port`. Debe implementar correctamente el ciclo de vida/servicio foreground de
  la versión Android usada y las acciones del sistema de Always-on.
- VpnService real con permiso BIND_VPN_SERVICE y soporte Always-on. Debe proteger
  los sockets de transporte necesarios para evitar bucles y manejar la interfaz
  TUN IPv4/IPv6, DNS y reconexión. Un proxy HTTP CONNECT de proxy.py no ofrece
  automáticamente transporte UDP/QUIC: el helper debe encapsularlo en un protocolo
  soportado o bloquearlo explícitamente. Su política debe ser comprobada.
- Provider `content://org.agx.vpntunnel.status`, método `status`. Validar el UID o
  permiso autorizado del llamador, sin exponer credenciales. La respuesta ADB
  debe incluir `status=` seguido de JSON en un Bundle. Recibe un extra
  `nonce:s:VALOR` y debe devolver el mismo nonce en una respuesta fresca.
- JSON: `nonce`, `package`, `host`, `port` (entero), `interface` (p. ej. tun0),
  `routes` con `0.0.0.0/0` y `::/0` o `ipv6_blocked: true`, `public_ip`, y booleanos
  `consent_granted`, `vpn_active`, `always_on`, `lockdown`, `dns_protected`,
  `probe_through_vpn`. Always-on/lockdown deben provenir de las APIs VpnService
  reales, no de copiar settings secure. La IP debe proceder de una solicitud HTTPS
  nueva que el helper envíe por la TUN, sin proteger ese socket para evitarla.

El controlador verifica los ajustes, el nonce y ese contrato antes de permitir
el ciclo. Reporta `configuracion_vpn_verificada: true` cuando corresponda, pero
mantiene `aislamiento_acreditado: false`: estas observaciones del helper no son
una prueba independiente de ausencia de fugas. Antes de producción comprobar
IPv4/IPv6, DNS, TCP/UDP/QUIC, caída del túnel, cambio de WiFi y reconexión mediante
observación del tráfico en el gateway. No se inventan esas mediciones.

## Recuperación y auditoría

Se guarda un lease propio con los valores previos de las tres claves secure y
el servidor/transporte ADB. No se sustituye una VPN Always-on previa. La app
controlada se detiene antes de retirar la política; se restauran los valores
anteriores y se detiene el servicio del helper. Cuando antes no existían claves,
se eliminan, incluida la allowlist.
El servicio de configuración debe cerrar también la TUN al detenerse. El provider
de estado debe seguir pudiendo responder y devolver `vpn_active: false`; si no
se confirma esa desconexión, la restauración se considera pendiente.

El supervisor recupera `vpn_lease.json` tras interrupciones. Si no se puede
confirmar la restauración, conserva el lease y la cuarentena SQLite. No se promete
«0 reservas» ante un dispositivo desconectado. El `finally` puede intentar
limpiar, pero no garantiza que Android responda.

No se desinstala automáticamente el APK ni se borran políticas sin un lease propio.
La función de restauración es idempotente y no elimina reservas de otros workers.

Fuentes oficiales:
[VpnService y consentimiento](https://developer.android.com/reference/android/net/VpnService),
[Always-on y bloqueo sin VPN](https://developer.android.com/develop/connectivity/vpn).

## Compilación local y portabilidad

```powershell
.\.venv\Scripts\python.exe scripts/compilar_helper.py
.\.venv\Scripts\python.exe scripts/compilar_helper.py --verify-only
```

Requiere un JDK y SDK Android con platform 35 y build-tools (aapt, d8, zipalign y
apksigner). Se detecta el SDK mediante `--sdk`, ANDROID_SDK_ROOT/ANDROID_HOME,
la ruta de ADB configurada y la instalación AGX adyacente. No descarga herramientas
ni instala el APK en las placas. El APK de laboratorio requiere Android 10 o
superior y target 32; adaptar el manifiesto y las pruebas para una distribución
de producción y versiones Android posteriores.

El pipeline compila Java, crea DEX, compila el manifiesto binario, incorpora DEX,
alinea, firma y verifica la firma antes de publicar el APK. La clave local de
laboratorio y su contraseña se guardan fuera del proyecto bajo LOCALAPPDATA,
con acceso restringido. Otra PC genera otra clave: no se sustituye automáticamente
una instalación firmada con una clave distinta ni se desinstala una VPN activa.

`runs/resultado_global.json` recibe `helper_apk_hash` y `helper_apk_info` sin borrar
otros campos. `--report` selecciona otro reporte. También se genera un manifiesto
local `.build.json` junto al APK. La firma criptográfica, la identidad del paquete
y el hash identifican un artefacto; no certifican enrutamiento, ausencia de fugas
o funcionamiento del stack TCP. El controlador rechaza este artefacto de control
como túnel funcional antes de instalarlo automáticamente.

`StreamBridge` usa dos pares de streams distintos y respeta half-close; no tiene
dos lectores compitiendo por el mismo InputStream. `HttpConnectTransport` protege
un socket por flujo, valida un CONNECT 200 y limita las cabeceras. `PacketPolicy`
descarta IPv4 fragmentado, UDP/QUIC, IPv6 y paquetes inválidos. El motor TCP debe
aplicar esa política, gestionar SYN/ACK, ventanas, checksums, retransmisiones,
reensamblado y escribir respuestas IP válidas en la TUN. También debe resolver
DNS sin UDP de salida; añadir 8.8.8.8 a Builder no implementa esa conversión.

## Consentimiento y telemetría

`otorgar_consentimiento_vpn_adb(device_id)` requiere USB y abre `.ConsentActivity`.
Solo pulsa una vez el botón positivo si la ventana enfocada es ConfirmDialog de
com.android.vpndialogs y el XML identifica AGX VPN Lockdown Helper. Verifica después
el consentimiento por el provider. Sin identificación suficiente, se solicita
intervención manual mediante un error auditable; no se envía Enter a ciegas.
El consentimiento no activa el motor ni libera reservas o cuarentenas SQLite.

`core.audit_artifacts.inyectar_perfil_en_auditoria` añade SDK, resolución y densidad
a `hardware_profiles`. No cambia `proxy_audit`, `ip_observada`, resultados previos
ni cuarentenas. Metadatos proporcionados no son pruebas de aislamiento de red.
