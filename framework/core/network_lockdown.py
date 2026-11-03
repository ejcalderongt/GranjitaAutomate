# PROPIEDAD INTELECTUAL - AGX FRAMEWORK | CONTROL AUTOMATIZADO DE RED LOCKDOWN VPN
"""Control ADB de un helper VPN real, con estado verificable y recuperación.

Requiere tools/agx_vpn_helper.apk y el contrato documentado en docs/LOCKDOWN_VPN.md.
No implementa el motor VPN ni convierte un proxy HTTP en un transporte UDP.
"""
from contextlib import contextmanager
import ipaddress
import json
from pathlib import Path
import re
import time
import hashlib
from uuid import uuid4
from defusedxml import ElementTree

from config.proxies import ADBError,adb,servidor_adb_actual,validar_proxy
from config.device_test import shell
from core.database import ROOT
from core.diagnostic_bridge import escribir_json
from core.network_isolation import directorio_red

PACKAGE='org.agx.vpntunnel'
SERVICE=PACKAGE+'/.VpnConfigService'
CONTROL=PACKAGE+'/.ControlReceiver'
KEYS=('always_on_vpn_app','always_on_vpn_lockdown_whitelist','always_on_vpn_lockdown')
SCOPE='VPN: ajustes + estado VpnService y sondeo declarados por el helper; no certifica ausencia de fugas independiente'


def _read(device,key):
    return shell(device,'settings','get','secure',key).strip()


def _lease(device,sessions=None):
    return directorio_red(device,sessions)/'vpn_lease.json'


def _load(device,sessions=None):
    path=_lease(device,sessions)
    data=json.loads(path.read_text(encoding='utf-8'))
    if data['serial']!=device or (tuple(data['server']) if data['server'] else None)!=servidor_adb_actual():
        raise ADBError('Lease VPN pertenece a otro transporte o servidor')
    return path,data


def verificar_lockdown(device_id,*,sessions=None):
    path,data=_load(device_id,sessions)
    if any(_read(device_id,key)!=value for key,value in data['applied'].items()):
        raise ADBError('Los ajustes VPN no coinciden con el lease')
    status=_helper_status(device_id)
    try:
        valid=(all(status.get(key) is True for key in ('consent_granted','vpn_active','always_on','lockdown',
                    'dns_protected','probe_through_vpn')) and
               status['host']==data['host'] and status['port']==data['port'] and
               '0.0.0.0/0' in status['routes'] and
               ('::/0' in status['routes'] or status.get('ipv6_blocked') is True) and
               bool(re.fullmatch(r'[A-Za-z0-9_.-]+',status['interface'])))
        observed=str(ipaddress.ip_address(status['public_ip']))
    except (KeyError,TypeError,ValueError):
        raise ADBError('Estado del helper VPN incompleto o inválido') from None
    if not valid:
        raise ADBError('Túnel, rutas, consentimiento o bloqueo no confirmados por VpnService')
    result={'lockdown_configurado':True,'vpn_activa':True,'aislamiento_acreditado':False,
            'configuracion_vpn_verificada':True,'endpoint':f"{data['host']}:{data['port']}",
            'public_ip':observed,'interface':status['interface'],'alcance':SCOPE}
    escribir_json(path.parent/'vpn_status.json',result)
    return result


def _helper_status(device_id):
    # Un provider real del helper debe responder a este nonce en una llamada nueva.
    nonce=uuid4().hex
    raw=shell(device_id,'content','call','--uri',f'content://{PACKAGE}.status',
              '--method','status','--extra',f'nonce:s:{nonce}',timeout=10)
    match=re.search(r'\bstatus\s*=\s*(\{)',raw)
    if not match:
        raise ADBError('Helper VPN sin estado verificable; se requiere consentimiento y contrato de estado')
    try:
        status=json.JSONDecoder().raw_decode(raw[match.start(1):])[0]
        valid=status['nonce']==nonce and status['package']==PACKAGE
    except (KeyError,TypeError,ValueError):
        raise ADBError('Estado del helper VPN incompleto o inválido') from None
    if not valid:
        raise ADBError('Respuesta VPN sin identidad o nonce vigente')
    return status


def _establecer_lockdown(device_id,host_ip,puerto,*,sessions=None,apk_path=None):
    endpoint=validar_proxy(host_ip,puerto)
    host=str(ipaddress.ip_address(host_ip))
    path=_lease(device_id,sessions)
    if path.exists():
        raise ADBError('Recuperar la sesión VPN pendiente antes de iniciar otra')
    installed=f'package:{PACKAGE}' in shell(device_id,'pm','list','packages',PACKAGE).splitlines()
    apk=Path(apk_path or ROOT/'tools/agx_vpn_helper.apk')
    if not installed and not apk.is_file():
        raise ADBError('Falta tools/agx_vpn_helper.apk; no se modificaron ajustes VPN')
    metadata=apk.with_suffix('.build.json')
    if not installed and metadata.is_file():
        build=json.loads(metadata.read_text(encoding='utf-8'))
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=build.get('helper_apk_hash'):
            raise ADBError('Hash del APK diferente del reporte de compilación')
        if build.get('tcp_engine_included') is not True:
            raise ADBError('APK de control compilado sin motor TCP; no se instalará ni activará como túnel funcional')
    # Lockdown puede cortar el único ADB TCP y dejar una placa sin recuperación.
    if ':' in device_id or not adb('-s',device_id,'get-devpath').startswith('usb:'):
        raise ADBError('La primera validación Lockdown requiere ADB USB directo para conservar recuperación')
    previous={key:_read(device_id,key) for key in KEYS}
    if previous[KEYS[0]] not in ('','null'):
        raise ADBError('Existe una VPN Always-on previa; no se sustituirá automáticamente')
    if not installed:
        output=adb('-s',device_id,'install',str(apk.resolve()),timeout=120)
        if 'Success' not in output.splitlines() or not shell(device_id,'pm','path',PACKAGE).strip().startswith('package:'):
            raise ADBError('Instalación del helper no confirmada')
    status=_helper_status(device_id)
    if status.get('engine_available') is False:
        raise ADBError('Helper instalado sin motor TCP; no se habilitará Lockdown')
    if status.get('consent_granted') is not True:
        raise ADBError('Falta consentimiento VPN; ejecutar otorgar_consentimiento_vpn_adb por USB')
    path.parent.mkdir(parents=True,exist_ok=True)
    data={'serial':device_id,'server':servidor_adb_actual(),'host':host,'port':int(puerto),
          'previous':previous,'applied':dict(zip(KEYS,(PACKAGE,'','1')))}
    escribir_json(path,data)
    output=shell(device_id,'am','broadcast','-n',CONTROL,'--es','operation','start','--es','host',host,'--ei','port',str(puerto))
    if re.search(r'error|exception|permission denial|not allowed',output,re.I):
        raise ADBError('Servicio VPN no iniciado; comprobar consentimiento, manifiesto y política del dispositivo')
    for key,value in data['applied'].items():
        shell(device_id,'settings','put','secure',key,value)
        if _read(device_id,key)!=value:
            raise ADBError('Android no confirmó el ajuste VPN '+key)
    return verificar_lockdown(device_id,sessions=sessions)


def establecer_lockdown_vpn_sin_root(device_id,host_ip,puerto,*,sessions=None,apk_path=None):
    if _lease(device_id,sessions).exists():
        raise ADBError('Recuperar el lease VPN pendiente antes de iniciar otra sesión')
    try:
        return _establecer_lockdown(device_id,host_ip,puerto,sessions=sessions,apk_path=apk_path)
    except Exception:
        if _lease(device_id,sessions).exists():
            liberar_lockdown_dispositivo(device_id,sessions=sessions)
        raise


def liberar_lockdown_dispositivo(device_id,*,sessions=None):
    path=_lease(device_id,sessions)
    if not path.exists():
        return True  # No borrar una VPN sin lease propio.
    path,data=_load(device_id,sessions)
    for key in KEYS:
        if _read(device_id,key) not in (data['previous'][key],data['applied'][key]):
            raise ADBError('Configuración VPN modificada externamente; requiere revisión')
    try:
        # Quitar primero el bloqueo propio y restaurar el estado anterior completo.
        for key in (KEYS[2],KEYS[0],KEYS[1]):
            previous=data['previous'][key]
            if previous=='null':
                shell(device_id,'settings','delete','secure',key)
            else:
                shell(device_id,'settings','put','secure',key,previous)
            if _read(device_id,key)!=previous:
                raise ADBError('No se confirmó restauración de '+key)
        output=shell(device_id,'am','broadcast','-n',CONTROL,'--es','operation','stop')
        if re.search(r'error|exception|permission denial',output,re.I):
            raise ADBError('No se confirmó la parada del servicio VPN')
        if _helper_status(device_id).get('vpn_active') is not False:
            raise ADBError('No se confirmó la desconexión del túnel por el helper')
    except Exception as exc:
        escribir_json(path.parent/'vpn_restore_required.json',{'device_id':device_id,'error_type':type(exc).__name__})
        raise
    path.unlink()
    (path.parent/'vpn_restore_required.json').unlink(missing_ok=True)
    return True


class VPNCheck:
    def __init__(self,device,sessions):
        self.device,self.sessions=device,sessions

    def __call__(self):
        return verificar_lockdown(self.device,sessions=self.sessions)

    def endpoint(self):
        return self()['endpoint']

    def public_ip(self):
        return self()['public_ip']


@contextmanager
def lockdown_vpn(device_id,host,port,*,sessions):
    if _lease(device_id,sessions).exists():
        raise ADBError('Existe una sesión VPN pendiente; no se sobrescribirá')
    try:
        establecer_lockdown_vpn_sin_root(device_id,host,port,sessions=sessions)
        yield VPNCheck(device_id,sessions)
    finally:
        liberar_lockdown_dispositivo(device_id,sessions=sessions)


def _boton_consentimiento_vpn(xml,focus):
    focus_lines=[line for line in focus.splitlines() if 'mCurrentFocus' in line]
    if len(focus_lines)!=1 or not ('com.android.vpndialogs' in focus_lines[0] and 'ConfirmDialog' in focus_lines[0]):
        return None
    if len(xml)>2000000:
        raise ADBError('Jerarquía de consentimiento excesiva')
    root=ElementTree.fromstring(xml)
    labels=' '.join(node.get('text','')+' '+node.get('content-desc','') for node in root.iter()).casefold()
    if 'agx vpn lockdown helper' not in labels:
        return None
    buttons=[]
    for node in root.iter():
        if (node.get('package')=='com.android.vpndialogs' and node.get('resource-id')=='android:id/button1'
                and node.get('enabled')=='true' and node.get('clickable')=='true'):
            match=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',node.get('bounds',''))
            if match:
                x1,y1,x2,y2=map(int,match.groups())
                if 0<=x1<x2 and 0<=y1<y2:
                    buttons.append(((x1+x2)//2,(y1+y2)//2))
    return buttons[0] if len(buttons)==1 else None


def otorgar_consentimiento_vpn_adb(device_id,*,timeout=20,sessions=None):
    """Confirmar únicamente el diálogo de este helper por USB; no toca cuarentenas."""
    if not 1<=timeout<=60:
        raise ValueError('timeout requiere 1–60 segundos')
    if ':' in device_id or not adb('-s',device_id,'get-devpath').startswith('usb:'):
        raise ADBError('El consentimiento automatizado requiere USB directo')
    if _helper_status(device_id).get('consent_granted') is True:
        return True
    folder=directorio_red(device_id,sessions)/'consent'
    folder.mkdir(parents=True,exist_ok=True)
    remote='/data/local/tmp/agx-vpn-consent-'+uuid4().hex+'.xml'
    clicked=False
    shell(device_id,'am','start','-n',PACKAGE+'/.ConsentActivity')
    deadline=time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            if _helper_status(device_id).get('consent_granted') is True:
                escribir_json(folder/'consent.json',{'consent_granted':True,'clicked':clicked,'quarantine_released':False})
                return True
            if not clicked:
                focus=shell(device_id,'dumpsys','window','windows',timeout=5)
                shell(device_id,'uiautomator','dump','--compressed',remote,timeout=5)
                xml=shell(device_id,'cat',remote,timeout=5)
                button=_boton_consentimiento_vpn(xml,focus)
                if button:
                    (folder/'dialog.xml').write_text(xml,encoding='utf-8')
                    escribir_json(folder/'consent.json',{'consent_granted':False,'click_attempted':True,'quarantine_released':False})
                    clicked=True  # Registrar antes del efecto externo; no repetir en caso de timeout.
                    shell(device_id,'input','tap',str(button[0]),str(button[1]),timeout=5)
            time.sleep(.25)
        raise ADBError('Consentimiento no confirmado; verificar manualmente el diálogo y el provider del helper')
    finally:
        try:
            shell(device_id,'rm','-f',remote,timeout=5)
        except ADBError:
            pass
