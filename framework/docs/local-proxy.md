# Proxy local de laboratorio

Instalado y verificado el 2026-10-29, America/Guatemala.

## Estado instalado

- Software: proxy.py 2.4.10, instalado en `.venv` mediante PyPI.
- IPv4 actual del servidor: `192.168.1.199`.
- Puertos: **8001, 8002 y 8003**, con una misma IP pública real de salida.
- ACL: únicamente las direcciones conocidas de las placas, el servidor y loopback.
- Arranque automático **al iniciar sesión con el usuario labor** mediante
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PandaProxyLaboratorio`.
- Proceso en segundo plano, sin ventana; no es un servicio de arranque antes del login.

La descarga oficial de 3proxy fue bloqueada por Windows como software
potencialmente no deseado. No se añadieron exclusiones ni se desactivó la
protección. Se instaló proxy.py como alternativa autorizada.

La elevación para una regla adicional de firewall fue cancelada por Windows.
No se modificaron sus reglas. La configuración de red existente sí permite el
acceso: se verificaron túneles CONNECT y HTTPS desde tres placas reales en los
tres puertos, además de HTTPS desde Windows. No se abrió TikTok.

## Integración del framework

`config/proxy_pool.json` está en modo `laboratory`, con tres entradas habilitadas.
`config/local_proxy.local.json` contiene la escucha y los clientes permitidos.
Ambos archivos son privados y están excluidos de Git. Las copias previas del
pool y SQLite están en `data/local_proxy_install/`.

Los endpoints se reservan individualmente y se verifica su salida pública real.
La salida compartida se registra como `laboratory`, no como prueba de IPs únicas.
El modo `production` conserva sus restricciones de IPv4 pública y salida única.
Cambiar el modo de un endpoint con reserva activa o en cuarentena está bloqueado.

El arranque detecta la IPv4 privada de la interfaz que llega a las placas y
actualiza el perfil local si cambió por DHCP. También intenta observar por HTTPS
la salida pública actual. No modifica un pool en modo producción ni inventa IPs
si la consulta no está disponible. Las direcciones nuevas de placas deben
incorporarse a la ACL antes de utilizarlas.

## Verificación HTTPS de Android

Las tres placas de la prueba no incluyen curl. Para laboratorio se compiló una
sonda propia de 1,9 KB con JDK y D8 existentes en AGX. Ejecuta únicamente una
petición a `https://api.ipify.org` mediante proxy explícito, usando HttpsURLConnection,
los certificados del sistema y la verificación normal de hostname.

La sonda se copia a `/data/local/tmp/panda-egress-<hash>.jar` y se comprueba su
SHA-256 antes de ejecutarla con `app_process`. No instala APK, certificados,
binarios nativos ni modifica el proxy global del dispositivo durante el test.
Se usa como alternativa a curl únicamente cuando el worker está en modo laboratorio.

```powershell
# Comprobar sin lanzar apps ni cambiar configuración global de Android:
.\.venv\Scripts\python.exe scripts/verificar_proxy_local.py

# Habilitar el pool solo si pasan todas las verificaciones:
.\.venv\Scripts\python.exe scripts/verificar_proxy_local.py --enable

# Reconstruir la sonda con el SDK indicado en native_dependencies.local.json:
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/Build-EgressProbe.ps1
```

El resultado se guarda en `sessions/local_proxy/verification.json`. Los logs y
PID del proxy se guardan en ese mismo directorio. Para reproducir la instalación
Python: `.\.venv\Scripts\python.exe -m pip install -r requirements-laboratory.txt`.

## Operación

Recargar Streamlit. El Panel de Control identifica el modo de laboratorio;
Configuración y Pruebas muestra las tres entradas locales. El smoke recomendado
es tres placas, un ciclo. El proveedor de red externo no es necesario para este
perfil; OPENAI_API_KEY y los demás requisitos del worker siguen aplicando.

Si otra política de Windows bloquea el acceso más adelante,
`Configurar-Firewall-Proxy.cmd` solicita elevación al operador para crear una
regla específica de esos tres puertos y clientes. Es opcional en la instalación
actual. No se solicita elevación automáticamente al arrancar el proxy.

Para quitar el arranque automático, eliminar únicamente el valor
`PandaProxyLaboratorio` de la clave Run anterior. Para volver a producción,
detener primero la automatización, verificar la limpieza de reservas y restaurar
el pool desde el respaldo o configurar los endpoints externos.
