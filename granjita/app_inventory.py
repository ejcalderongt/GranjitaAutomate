"""Inventario privado de apps y cuentas: hechos separados de asignaciones."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import re
import socket
import xml.etree.ElementTree as ET
from .core import Adb
from .inventory import shell
from .diagnostics import traced,emit,stamp
from .app_sources import foreground_package

CATALOG={
 'tiktok':dict(name='TikTok',packages=['com.zhiliaoapp.musically','com.ss.android.ugc.trill','com.zhiliaoapp.musically.go']),
 'instagram':dict(name='Instagram',packages=['com.instagram.android','com.instagram.lite']),
 'x':dict(name='X',packages=['com.twitter.android']),
 'facebook':dict(name='Facebook',packages=['com.facebook.katana','com.facebook.lite']),
}
SCREEN_LABELS={'unknown':'Sin verificar','onboarding':'Configuración pendiente','login_prompt':'Login visible','profile_visible':'Perfil propio visible','feed_visible':'Feed visible · cuenta sin verificar','permission_dialog':'Diálogo de permisos visible','not_foreground':'App fuera de primer plano','unreadable':'Pantalla no comprobada','ambiguous':'Lectura ambigua'}
ACCOUNT_LABELS={'unknown':'Sin verificar','needs_setup':'Configuración pendiente','login_prompt':'Login visible','session_observed':'Sesión observada'}
PRESENCE_LABELS={'present':'Con cuenta · declarado','absent':'Sin cuenta · declarado','unknown':'Pendiente de declarar'}
METHOD_LABELS={'adb':'Android / ADB','uiautomator2':'Lectura de interfaz','manual':'Confirmación del operador'}


def audit_stamp():return datetime.now(timezone(timedelta(hours=-6))).isoformat(timespec='microseconds')


def app_profile(app_id):
    if app_id not in CATALOG:raise ValueError('Aplicación no admitida en el inventario.')
    return CATALOG[app_id]


def account_handle(value):
    value=value.strip().removeprefix('@') if isinstance(value,str) else ''
    if value and not re.fullmatch(r'[A-Za-z0-9._]{1,64}',value):
        raise ValueError('Usa únicamente el identificador público de la cuenta, sin correo, contraseña ni enlaces.')
    return '@'+value if value else ''


def query(adb,transport,command):
    """Comandos internos fijos. Un fallo nunca equivale a app no instalada."""
    raw=shell(adb,transport,command+'; __ga_app_rc=$?; printf "\\n__GA_APP_RC=%s\\n" "$__ga_app_rc"')
    match=re.search(r'\n__GA_APP_RC=(\d+)\s*$',raw)
    if not match or match.group(1)!='0':raise RuntimeError('No se confirmó una consulta Android del inventario.')
    return raw[:match.start()].strip()


@traced('apps.inventory.technical')
def collect_technical(row):
    from .automation import validate_target
    validate_target(row)
    adb=Adb(row['port'],timeout=8)
    raw=query(adb,row['serial'],'pm list packages --show-versioncode')
    installed={m.group(1):m.group(2) for m in re.finditer(r'^package:([A-Za-z0-9_.]+)(?:\s+versionCode:(\d+))?\s*$',raw,re.M)}
    if not installed:raise RuntimeError('La lista de paquetes no es reconocible; no se presume ausencia de apps.')
    current=foreground_package(query(adb,row['serial'],'dumpsys activity activities'))
    observations={}
    for app_id,profile in CATALOG.items():
        variants=[]
        for package in profile['packages']:
            if package not in installed:continue
            try:
                dump=query(adb,row['serial'],'dumpsys package '+package)
                version=re.search(r'^\s*versionName=([^\r\n]{1,120})',dump,re.M)
                version_name=version.group(1).strip() if version else None
            except Exception:version_name=None
            variants.append(dict(package=package,version_code=installed[package],version_name=version_name))
        observations[app_id]=dict(status='ok',installation='installed' if variants else 'not_installed',variants=variants,foreground=current in profile['packages'] if current else None,
            foreground_package=current if current in profile['packages'] else None,signal='package_list_and_foreground')
    validate_target(row)
    emit('apps.inventory','collected',count=len(observations))
    return observations


def classify_screen(xml,app_id):
    """Reglas conservadoras: nunca extraer @menciones de un feed como cuenta propia."""
    profile=app_profile(app_id)
    if len(xml.encode('utf-8'))>2_000_000:raise ValueError('La pantalla excede el límite de lectura.')
    root=ET.fromstring(xml)
    nodes=list(root.iter())
    own=[n for n in nodes if n.get('package') in profile['packages']]
    result=dict(status='ok',screen_state='unknown',account_state='unknown',observed_account='',confidence='low',signals=[],source_sha256=hashlib.sha256(xml.encode()).hexdigest(),adapter_version=1)
    permission_packages={'com.android.permissioncontroller','com.google.android.permissioncontroller','com.android.packageinstaller','com.google.android.packageinstaller'}
    if any(n.get('package') in permission_packages for n in nodes):
        result.update(screen_state='permission_dialog',signals=['android_permission_dialog']);return result
    if not own:result.update(screen_state='unreadable',signals=['no_target_nodes']);return result
    if app_id!='tiktok':
        result['signals']=['account_adapter_pending'];return result
    texts={n.get('text','').strip() for n in own if n.get('text','').strip()}
    lowered={t.casefold() for t in texts}
    onboarding={'te damos la bienvenida a tiktok','bienvenido a tiktok','welcome to tiktok','cuéntanos más cosas sobre ti','tell us more about yourself','elige tus intereses','choose your interests','¿cuándo naciste?','when is your birthday?'}
    if lowered & onboarding:
        result.update(screen_state='onboarding',account_state='needs_setup',confidence='high',signals=['tiktok_setup_title']);return result
    login={'iniciar sesión en tiktok','inicia sesión en tiktok','log in to tiktok','registrarse en tiktok','sign up for tiktok'}
    if lowered & login:
        result.update(screen_state='login_prompt',account_state='login_prompt',confidence='high',signals=['tiktok_login_title']);return result
    selected_profile=any((n.get('text','').casefold()=='perfil' or n.get('text','').casefold()=='profile' or n.get('content-desc','').casefold() in ('perfil','profile')) and (n.get('selected')=='true' or n.get('checked')=='true') for n in own)
    parents={child:parent for parent in nodes for child in parent}
    own_profile_button=any(n.get('text','').strip().casefold() in ('editar perfil','edit profile') and (n.get('clickable')=='true' or n.get('class','').endswith('Button') or parents.get(n) is not None and parents[n].get('clickable')=='true') for n in own)
    handles={account_handle(t) for t in texts if re.fullmatch(r'@[A-Za-z0-9._]{1,64}',t)}
    if selected_profile and own_profile_button:
        if len(handles)==1:
            result.update(screen_state='profile_visible',account_state='session_observed',observed_account=next(iter(handles)),confidence='high',signals=['profile_tab_selected','edit_profile_button','unique_handle']);return result
        result.update(screen_state='ambiguous',signals=['profile_without_unique_handle']);return result
    if lowered & {'para ti','for you'} and lowered & {'siguiendo','following'}:
        result.update(screen_state='feed_visible',signals=['feed_tabs']);return result
    result['signals']=['no_account_proof']
    return result


class InspectionSession:
    """Sesión UiAutomator2 sin APK propia, sin lanzamiento ni cierre de la app actual."""
    def __init__(self,row):self.row=row;self.id=None
    def __enter__(self):
        from .automation import validate_target,start_appium,http,capabilities
        validate_target(self.row);start_appium()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        caps=capabilities(self.row,port)
        for key in ('appium:app','appium:appPackage','appium:appActivity','appium:enforceAppInstall'):caps.pop(key,None)
        caps.update({'appium:autoLaunch':False,'appium:forceAppLaunch':False,'appium:shouldTerminateApp':False,'appium:dontStopAppOnReset':True})
        self.id=http('POST','/session',{'capabilities':{'alwaysMatch':caps,'firstMatch':[{}]}})['sessionId']
        return self
    def source(self):
        from .automation import http
        return http('GET','/session/'+self.id+'/source',timeout=30)
    def __exit__(self,*args):
        from .automation import http
        if self.id:
            try:http('DELETE','/session/'+self.id,timeout=15)
            except Exception:pass


@traced('apps.inventory.screen')
def inspect_screen(row,app_id):
    from .automation import validate_target
    profile=app_profile(app_id)
    validate_target(row)
    adb=Adb(row['port'])
    before=foreground_package(query(adb,row['serial'],'dumpsys activity activities'))
    if before not in profile['packages']:
        return dict(status='ok',screen_state='not_foreground' if before else 'unreadable',account_state='unknown',observed_account='',confidence='low',signals=['target_not_foreground'])
    with InspectionSession(row) as session:
        xml=session.source()
        result=classify_screen(xml,app_id)
    after=foreground_package(query(adb,row['serial'],'dumpsys activity activities'))
    validate_target(row)
    if before!=after:return dict(status='error',screen_state='unreadable',account_state='unknown',observed_account='',confidence='low',signals=['foreground_changed'])
    result['package']=before
    emit('apps.inventory','screen_classified',state=result['screen_state'])
    return result


class AppInventory:
    def __init__(self,store):self.store=store
    def _identity(self,db,row):
        identifier=self.store.identity_family_db(db,row['id'])[0]
        identity=db.execute('SELECT hardware_serial FROM device_identity WHERE device_id=?',(identifier,)).fetchone()
        if not identity or identity['hardware_serial']!=row.get('hardware_serial'):raise ValueError('La identidad de la ficha cambió; vuelve a comprobar conexiones.')
        return identifier
    def observe(self,row,app_id,scope,payload,method):
        app_profile(app_id)
        if scope not in ('technical','screen') or method not in METHOD_LABELS:raise ValueError('Observación no admitida.')
        allowed={'status','installation','variants','foreground','foreground_package','signal','screen_state','account_state','observed_account','confidence','signals','source_sha256','adapter_version','package','error_class'}
        if not isinstance(payload,dict) or set(payload)-allowed:raise ValueError('La evidencia contiene campos no admitidos.')
        payload=dict(payload)
        if payload.get('status') not in ('ok','error'):raise ValueError('Resultado de observación inválido.')
        if scope=='technical' and method!='adb' or scope=='screen' and method=='adb':raise ValueError('Método incompatible con el tipo de evidencia.')
        if scope=='technical' and payload['status']=='ok':
            if payload.get('installation') not in ('installed','not_installed') or not isinstance(payload.get('variants'),list):raise ValueError('Evidencia de instalación inválida.')
            if bool(payload['variants'])!=(payload['installation']=='installed'):raise ValueError('La instalación no coincide con sus variantes.')
            for variant in payload['variants']:
                if not isinstance(variant,dict) or set(variant)!={'package','version_code','version_name'} or variant['package'] not in CATALOG[app_id]['packages']:raise ValueError('Variante no admitida.')
                if variant['version_name'] is not None and (not isinstance(variant['version_name'],str) or len(variant['version_name'])>120 or '\n' in variant['version_name']):raise ValueError('Versión inválida.')
        if scope=='screen' and payload.get('account_state')=='session_observed' and (payload.get('screen_state')!='profile_visible' or not payload.get('observed_account')):raise ValueError('Falta cuenta visible para observar sesión.')
        if 'observed_account' in payload:payload['observed_account']=account_handle(payload['observed_account'])
        if scope=='screen' and payload.get('observed_account') and payload.get('account_state')!='session_observed':raise ValueError('No atribuyas una cuenta a una pantalla sin prueba de sesión observada.')
        if scope=='screen' and (payload.get('screen_state') not in SCREEN_LABELS or payload.get('account_state') not in ACCOUNT_LABELS):raise ValueError('Estado de pantalla/cuenta inválido.')
        with self.store.connect() as db:
            identifier=self._identity(db,row)
            db.execute('INSERT INTO device_app_observations(device_id,hardware_serial,app_id,at,scope,method,payload) VALUES(?,?,?,?,?,?,?)',(identifier,row['hardware_serial'],app_id,audit_stamp(),scope,method,json.dumps(payload,ensure_ascii=False,sort_keys=True)))
    def declare_batch(self,entries,app_id,source):
        """Declaración humana sin inventar identificadores ni comprobar sesiones."""
        app_profile(app_id)
        if source not in ('user_report','operator_panel'):raise ValueError('Fuente manual inválida.')
        if not entries:raise ValueError('Listado vacío.')
        at=audit_stamp()
        with self.store.connect() as db:
            prepared=[];seen=set()
            for row,present,number in entries:
                if type(present) is not bool or type(number) is not int or number<1:raise ValueError('Declaración inválida.')
                identifier=self._identity(db,row)
                if identifier in seen:raise ValueError('Dispositivo repetido en el listado.')
                seen.add(identifier)
                payload=dict(status='ok',presence='present' if present else 'absent',source=source,panda_number=number)
                prepared.append((identifier,row['hardware_serial'],app_id,at,'declaration','manual',json.dumps(payload,sort_keys=True)))
            db.executemany('INSERT INTO device_app_observations(device_id,hardware_serial,app_id,at,scope,method,payload) VALUES(?,?,?,?,?,?,?)',prepared)
        return len(prepared)
    def assign(self,row,app_id,account):
        app_profile(app_id);account=account_handle(account)
        with self.store.connect() as db:
            identifier=self._identity(db,row)
            db.execute('INSERT INTO device_app_assignments(device_id,hardware_serial,app_id,at,expected_account) VALUES(?,?,?,?,?)',(identifier,row['hardware_serial'],app_id,audit_stamp(),account))
    def confirm(self,row,app_id,account,state):
        account=account_handle(account)
        if state not in ACCOUNT_LABELS:raise ValueError('Estado manual no admitido.')
        if state=='session_observed' and not account:raise ValueError('Indica la cuenta visible para confirmar sesión observada.')
        if state!='session_observed' and account:raise ValueError('Solo registra una cuenta observada cuando confirmas su sesión visible.')
        self.observe(row,app_id,'screen',dict(status='ok',screen_state='profile_visible' if state=='session_observed' else 'onboarding' if state=='needs_setup' else 'login_prompt' if state=='login_prompt' else 'unknown',account_state=state,observed_account=account,confidence='operator',signals=['operator_confirmation']), 'manual')
    def history(self,row,app_id):
        app_profile(app_id)
        with self.store.connect() as db:
            ids=self.store.identity_family_db(db,row['id']);marks=','.join('?' for _ in ids)
            observations=[dict(r) for r in db.execute('SELECT * FROM device_app_observations WHERE device_id IN ('+marks+') AND app_id=? ORDER BY id DESC LIMIT 200',(*ids,app_id))]
            assignments=[dict(r) for r in db.execute('SELECT * FROM device_app_assignments WHERE device_id IN ('+marks+') AND app_id=? ORDER BY id DESC LIMIT 100',(*ids,app_id))]
        for r in observations:r['payload']=json.loads(r['payload'])
        return dict(observations=observations,assignments=assignments)
    def view(self,row,app_id):
        app_profile(app_id)
        with self.store.connect() as db:
            ids=self.store.identity_family_db(db,row['id']);marks=','.join('?' for _ in ids)
            def latest(scope):
                found=db.execute('SELECT * FROM device_app_observations WHERE device_id IN ('+marks+') AND app_id=? AND scope=? ORDER BY id DESC LIMIT 1',(*ids,app_id,scope)).fetchone()
                if not found:return None
                value=dict(found);value['payload']=json.loads(value['payload']);return value
            technical=latest('technical');screen=latest('screen');declaration=latest('declaration')
            assignment=db.execute('SELECT * FROM device_app_assignments WHERE device_id IN ('+marks+') AND app_id=? ORDER BY id DESC LIMIT 1',(*ids,app_id)).fetchone()
        tp=technical['payload'] if technical else {};sp=screen['payload'] if screen else {}
        expected=assignment['expected_account'] if assignment else ''
        observed=sp.get('observed_account','')
        fresh=bool(screen and datetime.fromisoformat(screen['at'])>=datetime.fromisoformat(stamp())-timedelta(hours=24))
        assignment_checked=not assignment or bool(screen and screen['at']>assignment['at'])
        verified=sp.get('status')=='ok' and sp.get('account_state')=='session_observed' and bool(observed) and fresh and assignment_checked and tp.get('installation')!='not_installed'
        match='match' if verified and expected and expected.casefold()==observed.casefold() else 'mismatch' if verified and expected else 'unassigned' if not expected else 'unverified'
        return dict(declared_panda_number=declaration['payload']['panda_number'] if declaration else None,declared_presence=declaration['payload']['presence'] if declaration else 'unknown',declaration_at=declaration['at'] if declaration else None,declaration_source=declaration['payload']['source'] if declaration else None,device_id=row['id'],app_id=app_id,expected_account=expected,observed_account=observed,account_state=sp.get('account_state','unknown'),screen_state=sp.get('screen_state','unknown'),
            installation=tp.get('installation','unknown'),variants=tp.get('variants',[]),foreground=tp.get('foreground'),technical_status=tp.get('status','unknown'),technical_at=technical['at'] if technical else None,
            observed_at=screen['at'] if screen else None,method=screen['method'] if screen else None,confidence=sp.get('confidence','none'),screen_status=sp.get('status','unknown'),fresh=fresh,assignment_checked=assignment_checked,match=match)
