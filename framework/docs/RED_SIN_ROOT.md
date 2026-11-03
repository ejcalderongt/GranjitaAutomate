# Red Android de laboratorio sin root

Seleccionar «Control de red Android → Laboratorio sin root» antes del smoke test,
o ejecutar:

```powershell
.\.venv\Scripts\python.exe main.py --smoke-test 3 --cycles 1 --network-mode proxy-laboratory
```

Este modo requiere que `config/proxy_pool.json` declare `mode: laboratory`.
No reemplaza silenciosamente el modo predeterminado `root`.

El worker detiene TikTok, guarda `http_proxy` y `mobile_data` en un lease, configura
el endpoint y solicita `svc data disable`. Confirma los ajustes por lectura,
reserva exclusiva e IP HTTPS observada antes de abrir la app. La supervisión
vuelve a revisar los ajustes y la salida. El control no acredita la desactivación
física de todas las interfaces/SIM ni el enrutamiento del tráfico de TikTok.

El proxy de Android es una recomendación para aplicaciones compatibles; no es
una regla de un gateway y una app puede ignorarlo. Desactivar datos móviles no
bloquea TCP/UDP, QUIC, DNS o IPv6 directos por WiFi. Un proxy.py local tampoco
convierte automáticamente el equipo Windows en un gateway restrictivo ni crea
IPs residenciales distintas. Los tres puertos actuales comparten salida pública.

Fuentes: [Android LinkProperties](https://developer.android.com/reference/android/net/LinkProperties#setHttpProxy(android.net.ProxyInfo))
y [VPN Android y bloqueo sin VPN](https://developer.android.com/develop/connectivity/vpn).

Al finalizar, el worker detiene la app y restaura exactamente los ajustes previos.
El supervisor repite la recuperación si hubo interrupción. Si no puede verificarla,
conserva el lease, escribe `network_restore_required.json` y mantiene cuarentena;
no se anuncia un pool limpio sin comprobarlo. No se sobrescribe un proxy que un
operador haya cambiado durante la ejecución. La lectura de un estado de datos
móviles desconocido impide iniciar cambios que no podrían restaurarse.

`establecer_aislamiento_sin_root` conserva el nombre solicitado por compatibilidad,
pero su resultado declara `aislamiento_acreditado: false`; no certifica un perímetro.
`restaurar_red_dispositivo` restaura ajustes, no elimina reservas SQLite ajenas.
El supervisor es quien finaliza la reserva después de comprobar la restauración.
No se ejecutan funciones Streamlit desde los workers Android ni se usan acciones
de Playwright para controlar una placa ADB.
