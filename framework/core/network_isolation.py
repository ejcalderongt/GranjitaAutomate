"""Proxy Android de laboratorio sin root; no constituye aislamiento perimetral."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from config.device_test import shell
from config.proxies import ADBError,configurar_proxy_dispositivo,servidor_adb_actual,validar_proxy
from core.database import ROOT
from core.diagnostic_bridge import escribir_json

SCOPE='Laboratorio sin root: proxy global + datos móviles desactivados; no bloquea salida directa por WiFi'


def directorio_red(device_id,sessions=None):
    if sessions is not None:
        return Path(sessions)
    key=hashlib.sha256(repr((device_id,servidor_adb_actual())).encode()).hexdigest()[:24]
    return ROOT/'sessions/network'/key


def establecer_aislamiento_sin_root(device_id,host_ip_servidor,puerto_asignado,*,sessions=None):
    """Nombre compatible del panel; devuelve comprobaciones, NO aislamiento acreditado.

    El llamador debe detener la app antes de modificar/restaurar sus ajustes.
    No crea ni libera reservas SQLite; esa responsabilidad pertenece al supervisor.
    """
    endpoint=validar_proxy(host_ip_servidor,puerto_asignado)
    folder=directorio_red(device_id,sessions)
    lease=folder/'proxy_lease.json'
    folder.mkdir(parents=True,exist_ok=True)
    if lease.exists():
        raise ADBError('Restaurar el lease de red anterior antes de configurar otra sesión')
    previous=shell(device_id,'settings','get','global','http_proxy').strip()
    mobile=shell(device_id,'settings','get','global','mobile_data').strip()
    if mobile not in ('0','1'):
        raise ADBError('Estado previo de datos móviles no verificable; no se modificó la red')
    data={'mode':'proxy_laboratory','serial':device_id,'server':servidor_adb_actual(),
          'proxy':endpoint,'previous_proxy':previous,'previous_mobile_data':mobile,
          'isolation_verified':False,'scope':SCOPE}
    escribir_json(lease,data)  # Antes de cualquier cambio de resultado potencialmente incierto.
    configurar_proxy_dispositivo(device_id,host_ip_servidor,puerto_asignado)
    if mobile=='1':
        shell(device_id,'svc','data','disable')
    verificar_red_laboratorio(device_id,sessions=folder)
    escribir_json(folder/'network_guard.json',data)
    return {'proxy_confirmado':True,'datos_moviles_configurados':'0',
            'aislamiento_acreditado':False,'alcance':SCOPE}


def verificar_red_laboratorio(device_id,*,sessions=None):
    lease=directorio_red(device_id,sessions)/'proxy_lease.json'
    data=json.loads(lease.read_text(encoding='utf-8'))
    if data['mode']!='proxy_laboratory' or data['serial']!=device_id or (
            tuple(data['server']) if data['server'] else None)!=servidor_adb_actual():
        raise ADBError('Lease no corresponde al dispositivo o servidor ADB actual')
    if shell(device_id,'settings','get','global','http_proxy').strip()!=data['proxy']:
        raise ADBError('El proxy global cambió durante la prueba')
    if shell(device_id,'settings','get','global','mobile_data').strip()!='0':
        raise ADBError('Datos móviles no confirmados como desactivados')


def restaurar_red_dispositivo(device_id,*,sessions=None):
    folder=directorio_red(device_id,sessions)
    lease=folder/'proxy_lease.json'
    if not lease.exists():
        return True
    data=json.loads(lease.read_text(encoding='utf-8'))
    if data.get('mode')!='proxy_laboratory' or data['serial']!=device_id or (
            tuple(data['server']) if data['server'] else None)!=servidor_adb_actual():
        raise ADBError('No se modificará una sesión de red ajena')
    errors=[]
    try:
        current=shell(device_id,'settings','get','global','http_proxy').strip()
        previous=data['previous_proxy']
        if current not in (data['proxy'],previous):
            raise ADBError('El proxy fue modificado externamente; requiere revisión')
        if current!=previous:
            if previous in ('','null'):
                shell(device_id,'settings','delete','global','http_proxy')
            else:
                shell(device_id,'settings','put','global','http_proxy',previous)
        if shell(device_id,'settings','get','global','http_proxy').strip() not in (previous,'null' if not previous else previous):
            raise ADBError('No se confirmó la restauración del proxy')
    except Exception as exc:
        errors.append(type(exc).__name__+': proxy')
    try:
        current=shell(device_id,'settings','get','global','mobile_data').strip()
        previous=data['previous_mobile_data']
        if current!=previous:
            if previous!='1' or current!='0':
                raise ADBError('Datos móviles modificados externamente; requiere revisión')
            shell(device_id,'svc','data','enable')
        if shell(device_id,'settings','get','global','mobile_data').strip()!=previous:
            raise ADBError('No se confirmó restauración de datos móviles')
    except Exception as exc:
        errors.append(type(exc).__name__+': datos móviles')
    if errors:
        escribir_json(folder/'network_restore_required.json',{'device_id':device_id,'errors':errors})
        raise ADBError('Restauración de red pendiente: '+', '.join(errors))
    lease.unlink()
    (folder/'network_restore_required.json').unlink(missing_ok=True)
    return True


@contextmanager
def proxy_laboratorio_sin_root(device_id,host,port,*,sessions):
    try:
        establecer_aislamiento_sin_root(device_id,host,port,sessions=sessions)
        yield lambda:verificar_red_laboratorio(device_id,sessions=sessions)
    finally:
        restaurar_red_dispositivo(device_id,sessions=sessions)
