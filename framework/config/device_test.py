"""Preflight de una placa USB y ejecución opcional del feed IA/ADB."""
import ipaddress
import shlex
import signal
import time
from contextlib import contextmanager

from config.proxies import (
    ADBError, adb, verificar_adb, validar_proxy,
    configurar_proxy_dispositivo, limpiar_proxy_dispositivo,
)


def primer_dispositivo_usb():
    output = adb('devices', '-l')
    for line in output.splitlines():
        parts = line.split()
        # La propiedad usb: identifica el transporte físico; excluye emuladores/TCP.
        if len(parts) >= 2 and parts[1] == 'device' and any(
            value.startswith('usb:') for value in parts[2:]
        ):
            return parts[0]
    raise ADBError('No hay dispositivo USB autorizado en estado device. '
                   'Revisa adb devices -l, el driver USB de Windows y acepta la clave RSA en Android. '
                   f'Inventario recibido: {output[:1000]}')


def shell(device_id, *args, timeout=20):
    # ADB combina argumentos para el shell remoto: citar también para Android.
    return adb('-s', device_id, 'shell', shlex.join(args), timeout=timeout)


def consultar_ip(device_id, proxy=None,*,allow_native=False):
    """HTTPS con proxy explícito; sonda nativa opcional para laboratorio sin curl."""
    try:
        shell(device_id, 'curl', '--version')
    except ADBError as exc:
        if allow_native and proxy:
            from core.egress_probe import consultar_salida_nativa
            return consultar_salida_nativa(device_id,proxy)
        raise ADBError('Se requiere curl con HTTPS en Android para verificar la IP '
                       'automáticamente. No se instalaron binarios ni se abrió TikTok. '
                       'Comprueba también la conexión USB.') from exc
    # -q debe ser el primer argumento: ignorar .curlrc. Vaciar no_proxy fuerza
    # el proxy explícito; en modo directo --noproxy * evita variables heredadas.
    options = ['curl', '-q', '--fail', '--silent', '--show-error',
               '--connect-timeout', '10', '--max-time', '25',
               '--proto', '=https', '--proxy', f'http://{proxy}' if proxy else '',
               '--noproxy', '' if proxy else '*', 'https://api.ipify.org']
    output = shell(device_id, *options, timeout=30)
    try:
        return str(ipaddress.ip_address(output.strip()))
    except ValueError as exc:
        raise ADBError(f'ipify no devolvió una IP válida: {output[:120]!r}') from exc


@contextmanager
def proxy_temporal(device_id, host, port):
    """Limpieza incluso si la escritura tuvo éxito pero falló su verificación."""
    try:
        configurar_proxy_dispositivo(device_id, host, port)
        yield
    finally:
        for attempt in range(3):
            try:
                limpiar_proxy_dispositivo(device_id)
                print(f'Proxy eliminado en {device_id}: :0', flush=True)
                break
            except ADBError:
                if attempt == 2:
                    raise ADBError(
                        f'NO se pudo confirmar cleanup en {device_id}. Reconecta USB y ejecuta: '
                        f'adb -s {device_id} shell settings put global http_proxy :0')
                time.sleep(1)


def ejecutar_prueba_dispositivo(proxy, expected_ip, *, package=None, activity=None, map_ui=False, ai_videos=0):
    verificar_adb()
    host, port = proxy.rsplit(':', 1)
    endpoint = validar_proxy(host, port)
    expected = str(ipaddress.ip_address(expected_ip))
    device_id = primer_dispositivo_usb()
    print(f'Dispositivo USB seleccionado: {device_id}', flush=True)
    previous = signal.getsignal(signal.SIGTERM)

    def terminar(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminar)
    try:
        with proxy_temporal(device_id, host, int(port)):
            actual = consultar_ip(device_id, endpoint)
            print(f'IP pública observada por curl Android vía proxy: {actual}', flush=True)
            if actual != expected:
                raise ADBError(f'IP de salida inesperada: {actual}; esperada: {expected}. '
                               'TikTok no se abrirá.')
            print('IP de salida coincide. Esto verifica curl por proxy, '
                  'no DNS ni el tráfico de TikTok.', flush=True)
            if activity:
                from config.android_app import normalizar_activity, validar_componente_instalado, TIKTOK_PACKAGE
                if package==TIKTOK_PACKAGE:
                    activity=normalizar_activity(package,activity)
                    validar_componente_instalado(device_id,package,activity)
                from config.network_guard import trafico_restringido
                from core.selectors import capturar_pantalla_y_xml
                # start -n por sí solo no detiene un proceso existente.
                shell(device_id, 'am', 'force-stop', package)
                component = f'{package}/{activity}'
                with trafico_restringido(device_id, host, int(port)) as verificar_red:
                    try:
                        if consultar_ip(device_id, endpoint) != expected:
                            raise ADBError('La IP cambió bajo aislamiento; arranque cancelado')
                        result = shell(device_id, 'am', 'start', '-W', '-n', component)
                        if 'Error' in result or 'Exception' in result or 'Status: ok' not in result:
                            raise ADBError(f'No se confirmó el arranque: {result[:500]}')
                        time.sleep(2)

                        def comprobar_conexion_y_red():
                            if adb('-s', device_id, 'get-state') != 'device':
                                raise ADBError('Dispositivo USB desconectado')
                            verificar_red()

                        if ai_videos:
                            from core.ai_orchestrator import ejecutar_feed
                            ejecutar_feed(device_id,package=package,videos=ai_videos,
                                          check=comprobar_conexion_y_red,proxy=endpoint)
                        else:
                            capturar_pantalla_y_xml(device_id)
                            print('TikTok abierto bajo firewall. Ctrl+C detiene la app y limpia.', flush=True)
                            while True:
                                comprobar_conexion_y_red()
                                time.sleep(1)
                    finally:
                        shell(device_id, 'am', 'force-stop', package)
            elif map_ui:
                from core.selectors import capturar_pantalla_y_xml
                capturar_pantalla_y_xml(device_id)
            return {'udid': device_id, 'observed_ip': actual, 'expected_ip': expected,
                    'match': True, 'scope': 'android_curl_explicit_proxy', 'dns_tested': False}
    finally:
        signal.signal(signal.SIGTERM, previous)
