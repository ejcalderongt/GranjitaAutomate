# Binding tun2socks del host y separación de Android

## Instalación en Windows

```powershell
.\.venv\Scripts\python.exe scripts/preparar_tun2socks.py
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

La versión es `tun2socks==2.7.0.1`. El instalador soporta wheels verificadas de
CPython 3.11–3.14 Windows AMD64 convencional. Conserva la wheel en
`tools/tun2socks-python/wheelhouse` y las fuentes en `upstream-src`, con su licencia
MIT original. No las presenta como código propietario del framework. El bootstrap
web prepara esa wheelhouse antes de instalar requirements.

La fuente solicitada es `https://github.com/LorenEteval/tun2socks-python.git`.
El 29 de octubre de 2026 Git respondió Repository not found; los endpoints de
índice PyPI también devolvieron 404. Los artefactos publicados en files.pythonhosted
siguen accesibles. Por eso se recuperan el sdist y la wheel publicados por ese
proyecto, verificando sus SHA-256 contra la página de la versión. No se afirma que
se haya clonado Git con éxito ni se crea un repositorio sustituto.

El comando `git clone https://github.com` no identifica un repositorio.
Instalar directamente el sdist requiere Go, CMake y compilador C++; para evitar
esa compilación se instala la wheel local verificada, por ejemplo:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links tools/tun2socks-python/wheelhouse tun2socks==2.7.0.1
```

La procedencia y los hashes quedan en `runs/tun2socks-install.json`. En otra PC
ejecutar el instalador con el Python del .venv de destino; no copiar una wheel de
otro ABI. No se descargan binarios sin un hash esperado.

## Ejecución supervisada

`core.network_tunnel.iniciar_motor_tunel_tcp` acepta `device`, `networkInterface`,
`logLevel`, `proxy` y `restAPI`. Valida el hash del APK contra el archivo real y
exige `global_tests.status=passed` con la huella del código actual en
`runs/resultado_global.json`. `scripts/run_tests.py` actualiza esa prueba solamente
tras ejecutar la suite completa, sin filtros, y conservando las demás claves.

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe main.py --host-tunnel-check --tunnel-device tun0 --tunnel-proxy http://192.168.1.199:8001 --tunnel-rest-api 127.0.0.1:6060
```

El diagnóstico es acotado y no habilita despliegue Android. No modifica rutas
predeterminadas, DNS o políticas VPN de las placas. Windows necesita Wintun y los
permisos de TUN correspondientes; instalar la extensión Python no proporciona
necesariamente el driver. No se solicitan privilegios ni se instala un driver
automáticamente.

En la comprobación real de este entorno, el motor abrió REST y a continuación
terminó con `Error loading wintun.dll`. El supervisor conservó el framework y
registró `motor_tcp_estado: fallido`. La wheel está instalada; el driver/interfaz
Windows sigue pendiente. No se convirtió ese socket abierto en prueba de éxito.

La firma real de `startFromArgs` admite esos cinco argumentos y tres parámetros
opcionales de buffers TCP. El comodín lógico `networkInterface="any"` se traduce
a `""`, porque la implementación usa `net.InterfaceByName` para nombres no vacíos
y no reconoce `any` como comodín.

El código Go puede llamar a `log.Fatalf`, que termina el proceso incluso si la
API fue llamada desde un hilo. Para no cerrar Streamlit, el framework crea un
subproceso y dentro de él el `threading.Thread(daemon=True)` que invoca el binding.
El supervisor captura la salida, exit code, tiempo de espera y estado en
`runs/motor-tcp-*/`, y actualiza el reporte global de forma atómica.

`iniciando` o `iniciado_sin_validar_datos` no significan motor operativo. Se exige
REST `/netstats`, interfaz del host presente y una prueba de datos explícita
`ready_probe` que realmente observe tráfico a través de esa TUN para registrar
`motor_tcp_estado: activo`. Sin esa prueba el diagnóstico vence y detiene el hijo.
El callback debe ser acotado y no limitarse a abrir el socket del proxy.

La API Python publicada no expone Stop. El supervisor termina el hijo cuando
vence el diagnóstico y deja constancia de que se debe verificar la limpieza de
la interfaz del host. No anuncia restauración de rutas/DNS por el mero cierre.

## Por qué esto no desbloquea el APK

`tun0` en Windows y el descriptor creado por VpnService en Android pertenecen a
distintos sistemas operativos. Que el host abra un proxy o su API REST no le da
acceso al descriptor Android. El APK sigue sin contener la clase motor TCP y su
hash no acredita dicha integración.

El estado del binding usa scope `host_windows` y mantiene
`motor_tcp_android_deployment_ready: false`. No modifica
`helper_apk_info.tcp_engine_included` ni retira el preflight Android.
Para completar el túnel de las placas se necesita un motor compilado para cada
ABI Android, enlazado por JNI al descriptor de VpnService, con protección de sus
sockets y pruebas reales de tráfico/caída de túnel. Una extensión CPython de
Windows no puede empaquetarse como esa biblioteca Android.

Fuente de API y artefactos:
[Publicación oficial tun2socks 2.7.0.1](https://pypi.org/project/tun2socks/2.7.0.1/).
