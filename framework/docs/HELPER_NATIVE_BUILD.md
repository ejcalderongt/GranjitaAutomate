# Bibliotecas Android en el helper

El compilador acepta `--native-manifest archivo.json --require-native`.
El manifiesto contiene un objeto `libraries` con las claves `arm64-v8a`
y `armeabi-v7a`. Cada entrada requiere `url` (HTTPS directo al archivo ELF
compartido de un release fijado) y `sha256` (64 caracteres hexadecimales
publicados o verificados por el operador).

No se configura un origen predeterminado: `https://github.com` no identifica
un repositorio. Los archivos AAR y ZIP requieren extracción y revisión previa;
no son bibliotecas compartidas y el validador los rechaza.

```powershell
.\.venv\Scripts\python.exe scripts/compilar_helper.py --native-manifest config/helper-native.local.json --require-native
.\.venv\Scripts\python.exe scripts/compilar_helper.py --verify-only --require-native
```

Las descargas tienen timeout de 30 segundos y límite de 32 MiB por biblioteca.
Se verifican SHA-256, cabecera ELF, clase, endianness, tipo compartido y máquina
ARM/AArch64. Estas comprobaciones estructurales no demuestran compatibilidad
Android ni JNI. Se necesitan también la API mínima y las dependencias del
proveedor. El staging usa `src/main/jniLibs/<abi>/libtun2socks.so` y el APK
usa `lib/<abi>/libtun2socks.so`. Ambas arquitecturas y sus hashes se comprueban
antes de firmar; los hashes finales quedan registrados en la auditoría.

## Contrato pendiente del motor

`System.loadLibrary("tun2socks")` solo carga una biblioteca. No crea un puente
JNI ni implementa `tun2socks_start`. El proveedor debe suministrar el contrato
JNI real, su clase Java y la implementación `PacketEngine` que reciba la TUN
de `VpnConfigService`, además del cierre coordinado del descriptor y sockets.
El endpoint es la IP del host de control; `127.0.0.1` en Android apunta a la
propia placa, salvo que se ejecute allí un adaptador local.

El proyecto público `heiher/hev-socks5-tunnel` publica un AAR con JNI registrado
en `hev.htproxy.TProxyService`. Su protocolo es SOCKS5; no es un sustituto
directo del proxy HTTP CONNECT del laboratorio. Renombrar su biblioteca no
cambia el contrato JNI ni el protocolo.

Fuentes: https://github.com/heiher/hev-socks5-tunnel y
https://github.com/heiher/hev-socks5-tunnel/releases

Hasta integrar y probar ese contrato, `tcp_engine_included` y
`motor_tcp_android_deployment_ready` permanecen en falso, incluso si el APK
contiene las dos bibliotecas. El tamaño del APK y el hash no acreditan que
el túnel funcione ni que no existan fugas. No se instala ni activa este APK
automáticamente en las placas.

## Auditoría y mirrors (2026-10-30)

Se inspeccionaron 9 fuentes Java del helper: no hay declaraciones nativas,
llamadas loadLibrary ni archivos Smali. El APK actual contiene cero entradas
lib/. Las pruebas de estructura usan fixtures; no son binarios de producción.
El informe real se guarda en runs/jni-contract-audit.json.

Comandos PowerShell desde C:\Users\labor\OneDrive\Documents\ChatGPT\Framwork:

```powershell
.\.venv\Scripts\python.exe scripts/auditar_jni.py
rg -n 'loadLibrary|\bnative\b|\.method.*native' android/agx_vpn_helper
rg -n 'HttpConnectTcpEngine' android/agx_vpn_helper/src
```

Para una carpeta descompilada existente, pasar su ruta absoluta con --root.
No existe una carpeta de APK descompilado identificada en este proyecto.

scripts/helper_native.py intenta, para releases completos de github.com,
mirror.ghproxy.com, ghproxy.com y finalmente el origen. Cada intento conserva
HTTPS, timeout de 30 s, límite de 32 MiB y el SHA-256 fijado independientemente.
Una respuesta HTML o un hash incorrecto no se acepta. Estos dominios son
transportes solicitados por el operador; no se les atribuye confianza sobre
la autenticidad del motor. No se descargó un release: falta URL concreta y hash.

android/agx_vpn_helper/jni-template/tun2socks_jni.c documenta un contrato
PROPUESTO (ILjava/lang/String;I)V, no uno descubierto. Su función lanza una
excepción explícita hasta integrar la API del proveedor; está fuera de src y
no entra al APK. No implementa TCP, HTTP CONNECT, DNS ni transferencia del FD.
No se renombra una biblioteca de terceros ni se presume compatibilidad JNI.
