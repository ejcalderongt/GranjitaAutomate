"""Ejecutor de laboratorio Appium y adaptador explícito de Automate."""
from .diagnostics import traced, emit, span, context_map
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import hashlib

from .core import ROOT, DATA, Adb, now
from .inventory import shell, identity_from_properties

PACKAGE = 'gt.granjita.lab'
APPIUM_URL = 'http://127.0.0.1:4723'
ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'
_server = None
_server_lock = threading.Lock()


class AutomationError(Exception):
    pass


def http(method, path, data=None, timeout=180):
    payload = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(APPIUM_URL + path, data=payload, method=method, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        emit('appium.http','failure',status='error',http_status=exc.code)
        try:
            detail = json.load(exc)['value']['message']
        except Exception:
            detail = f'HTTP {exc.code}'
        raise AutomationError(str(detail)[:3000]) from exc
    value = result.get('value')
    if isinstance(value, dict) and value.get('error'):
        known={'no such element','invalid session id','timeout','unknown error','invalid argument','session not created','no such driver','stale element reference'}
        emit('appium.http','failure',status='error',error_code=value['error'] if value['error'] in known else 'unclassified')
        raise AutomationError(value.get('message', value['error']))
    return value


def runtime():
    path = DATA / 'automation-runtime.json'
    if not path.exists():
        raise AutomationError('Faltan herramientas. Ejecuta scripts.setup_automation y scripts.build_lab.')
    return json.loads(path.read_text(encoding='utf-8'))


def appium_status():
    try:
        value = http('GET','/status',timeout=3)
        return 'Disponible' if value.get('ready') else 'Ocupado'
    except Exception:
        return 'Detenido / no disponible'


@traced('appium.ensure')
def start_appium():
    global _server
    with _server_lock:
        if appium_status() != 'Detenido / no disponible':
            return
        config = runtime()
        env = os.environ.copy()
        env.update(APPIUM_HOME=config['appium_home'],ANDROID_HOME=config['sdk'],ANDROID_SDK_ROOT=config['sdk'],JAVA_HOME=config['java_home'])
        env['PATH'] = str(Path(config['node']).parent) + os.pathsep + str(ROOT/'.tools/bin') + os.pathsep + env.get('PATH','')
        log_path=DATA/'appium.log'
        with log_path.open('ab') as log:
            _server = subprocess.Popen([config['node'],config['appium'],'--address','127.0.0.1','--port','4723','--log-no-colors'],env=env,stdout=log,stderr=log,creationflags=0x08000000)
        for _ in range(60):
            if _server.poll() is not None:
                raise AutomationError('Appium no pudo iniciar. Consulta data/appium.log.')
            if appium_status() == 'Disponible':
                return
            time.sleep(0.5)
        raise AutomationError('Appium no respondió a tiempo. Consulta data/appium.log.')


@traced('identity.validate')
def validate_target(row):
    if row['status'] != 'Validado' or row.get('identity_state') != 'Serial leído':
        raise AutomationError('La placa debe estar validada y tener serial físico sin conflicto.')
    raw = shell(Adb(row['port']), row['serial'], 'getprop')
    identity = identity_from_properties(dict(re.findall(r'^\[([^]]+)\]: \[(.*)\]\r?$',raw,re.M)))
    if identity['identity_conflict'] or identity['hardware_serial'] != row.get('hardware_serial'):
        raise AutomationError('El serial actual no coincide con la ficha. Vuelve a buscar y validar.')


def capabilities(row, system_port):
    return {'platformName':'Android','appium:automationName':'UiAutomator2',
        'appium:udid':row['serial'],'appium:adbPort':row['port'],
        'appium:suppressKillServer':True,'appium:systemPort':system_port,
        'appium:app':str(DATA/'granjita-lab.apk'),'appium:appPackage':PACKAGE,
        'appium:appActivity':'.MainActivity','appium:noReset':True,
        'appium:forceAppLaunch':True,'appium:enforceAppInstall':True,'appium:shouldTerminateApp':True,
        'appium:skipDeviceInitialization':True,'appium:ignoreHiddenApiPolicyError':True,
        'appium:newCommandTimeout':120,'appium:androidInstallTimeout':90000,
        'appium:uiautomator2ServerInstallTimeout':90000,'appium:uiautomator2ServerLaunchTimeout':90000}


class Session:
    def __init__(self,row):
        self.row=row
        self.id=None

    @traced('appium.session.open')
    def __enter__(self):
        validate_target(self.row)
        if not (DATA/'granjita-lab.apk').is_file():
            raise AutomationError('Falta compilar data/granjita-lab.apk.')
        # noReset omite la actualización de APK en algunas versiones del driver.
        # Actualizar explícitamente SOLO la APK propia y preservar sus datos (-r).
        config=runtime()
        with span('appium.apk.install'):
            install=subprocess.run([str(Path(config['sdk'])/'platform-tools/adb.exe'),'-P',str(self.row['port']),'-s',self.row['serial'],'install','-r',str(DATA/'granjita-lab.apk')],capture_output=True,text=True,timeout=120,creationflags=0x08000000)
            if install.returncode or 'Success' not in install.stdout:
                raise AutomationError('No se pudo instalar Granjita Lab: '+(install.stdout+install.stderr)[-1500:])
        start_appium()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        with span('appium.session.create'):
            result=http('POST','/session',{'capabilities':{'alwaysMatch':capabilities(self.row,port),'firstMatch':[{}]}})
        self.id=result['sessionId']
        return self

    def call(self,method,path,data=None):
        route=re.sub(r'/element/[^/]+','/element/<id>',path)
        with span('appium.request',method=method,route=route or '/session'):
            result=http(method,f'/session/{self.id}'+path,data)
            emit('appium.request','response',response_type=type(result).__name__,response_bytes=len(result.encode('utf-8')) if isinstance(result,str) else 0)
            return result

    def element(self,description):
        deadline=time.monotonic()+15
        while True:
            try:
                return self.call('POST','/element',{'using':'accessibility id','value':description})[ELEMENT]
            except AutomationError:
                if time.monotonic()>deadline:
                    raise
                time.sleep(.4)

    def click(self,description):
        self.call('POST',f'/element/{self.element(description)}/click',{})

    def text(self,description):
        return self.call('GET',f'/element/{self.element(description)}/text')

    def __exit__(self,*args):
        if self.id:
            try:
                self.call('DELETE','')
            except Exception:
                pass


@traced('task.lab_smoke')
def run_lab(row, comment, task_id, cancelled=lambda:False):
    if len(comment)>280 or not comment.strip():
        raise AutomationError('Escribe un comentario local de 1 a 280 caracteres.')
    if cancelled():
        raise AutomationError('Cancelado antes de iniciar la sesión.')
    def checkpoint():
        if cancelled():
            raise AutomationError('Cancelado por el usuario.')
    with Session(row) as session:
        checkpoint()
        current=session.call('GET','/appium/device/current_package')
        if current != PACKAGE:
            raise AutomationError('La app de laboratorio no está en primer plano.')
        # Cada ejecución parte del inicio del feed, aunque la actividad haya conservado scroll.
        session.call('POST','/execute/sync',{'script':'mobile: scrollGesture','args':[{'elementId':session.element('lab_feed'),'direction':'up','percent':1.0,'speed':5000}]})
        for _ in range(12):
            source=session.call('GET','/source')
            if 'lab_like_01' in source:
                break
            session.call('POST','/execute/sync',{'script':'mobile: scrollGesture','args':[{'elementId':session.element('lab_feed'),'direction':'up','percent':1.0,'speed':5000}]})
        session.click('lab_like_01')
        if session.text('lab_like_01').upper() != 'ME GUSTA: SI':
            raise AutomationError('No se pudo verificar el like local.')
        checkpoint()
        element=session.element('lab_comment_01')
        session.call('POST',f'/element/{element}/clear',{})
        session.call('POST',f'/element/{element}/value',{'text':comment})
        try:
            session.call('POST','/appium/device/hide_keyboard',{})
        except AutomationError:
            pass
        session.click('lab_send_01')
        if session.text('lab_saved_01')!=comment:
            raise AutomationError('No se pudo verificar el comentario local.')
        checkpoint()
        def positions(source):
            return [(node.get('content-desc'),node.get('bounds')) for node in ET.fromstring(source).iter() if (node.get('content-desc') or '').startswith('lab_like_')]
        before=positions(session.call('GET','/source'))
        session.call('POST','/execute/sync',{'script':'mobile: scrollGesture','args':[{'elementId':session.element('lab_feed'),'direction':'down','percent':0.7}]})
        after=positions(session.call('GET','/source'))
        if not after or before == after:
            raise AutomationError('No se pudo verificar el desplazamiento del feed.')
        encoded=session.call('GET','/screenshot')
        evidence=DATA/'lab-evidence'
        evidence.mkdir(exist_ok=True)
        image=evidence/(task_id+'.png')
        image.write_bytes(base64.b64decode(encoded))
        return f'Like local, comentario y scroll verificados. Evidencia: {image.name}'


@traced('task.like')
def run_like(row, task_id, cancelled=lambda:False, audit=lambda kind,data:None):
    if cancelled():
        raise AutomationError('Cancelado antes de iniciar.')
    audit('started',{})
    with Session(row) as session:
        if session.call('GET','/appium/device/current_package') != PACKAGE:
            raise AutomationError('La app de laboratorio no está en primer plano.')
        if cancelled():raise AutomationError('Cancelado antes del like.')
        before=session.text('lab_like_01').upper()
        audit('observed',{'state':before})
        if before not in ('ME GUSTA: SI','ME GUSTA: NO'):
            raise AutomationError('Estado del botón desconocido; revisar sin pulsar.')
        if cancelled():raise AutomationError('Cancelado antes de pulsar.')
        if before=='ME GUSTA: NO':
            audit('click_requested',{})
            session.click('lab_like_01')
        if session.text('lab_like_01').upper()!='ME GUSTA: SI':
            raise AutomationError('Resultado del like sin confirmar; revisar antes de repetir.')
        audit('verified',{'outcome':'already_marked' if before=='ME GUSTA: SI' else 'applied','before':before,'after':'ME GUSTA: SI'})
        evidence=DATA/'lab-evidence';evidence.mkdir(exist_ok=True)
        path=evidence/(task_id+'.png')
        path.write_bytes(base64.b64decode(session.call('GET','/screenshot')))
        audit('evidence',{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        return ('Ya estaba marcado; no se volvió a pulsar.' if before=='ME GUSTA: SI' else 'Like local aplicado y verificado.') + ' Evidencia: '+path.name


@traced('automate.status')
def automate_status(row):
    validate_target(row)
    installed=bool(shell(Adb(row['port']),row['serial'],'pm path com.llamalab.automate'))
    if not installed:
        return 'No instalado. Instala Automate desde Google Play en esta placa.'
    enabled=shell(Adb(row['port']),row['serial'],'settings get secure enabled_accessibility_services')
    return 'Instalado · Accesibilidad ' + ('habilitada' if 'com.llamalab.automate/' in enabled else 'pendiente de habilitar por el usuario si el flujo la necesita')


@traced('automate.open')
def open_automate(row):
    status=automate_status(row)
    if status.startswith('No instalado'):
        raise AutomationError(status)
    result=shell(Adb(row['port']),row['serial'],'monkey -p com.llamalab.automate -c android.intent.category.LAUNCHER 1')
    return status+'\n'+result


class JobStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA/'automation.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            source=sqlite3.connect(self.path)
            try:
                if not source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='like_context'").fetchone():
                    destination=sqlite3.connect(self.path.with_name(self.path.stem+'-antes-metricas.sqlite3'))
                    try:source.backup(destination)
                    finally:destination.close()
            finally:source.close()
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,batch TEXT NOT NULL,device_id TEXT NOT NULL,name TEXT NOT NULL,
                port INTEGER NOT NULL,serial TEXT NOT NULL,action TEXT NOT NULL,comment TEXT NOT NULL,
                status TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pilot_devices(device_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS like_context(task_id TEXT PRIMARY KEY,context TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS like_events(id INTEGER PRIMARY KEY,task_id TEXT NOT NULL,at TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS like_events_task ON like_events(task_id,id);
                CREATE TABLE IF NOT EXISTS task_recipes(task_id TEXT PRIMARY KEY,recipe_id TEXT NOT NULL,spec TEXT NOT NULL,sha256 TEXT NOT NULL);
            ''')
            db.execute("UPDATE tasks SET status='Resultado incierto',detail='La aplicación se cerró durante una tarea. No se reintenta automáticamente.' WHERE status='Ejecutando'")
            db.execute("UPDATE tasks SET status='Interrumpido',detail='Lote interrumpido. Crear un nuevo lote para continuar.' WHERE status IN ('En cola','Programado')")

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self,rows,comment,action='lab_like_comment_scroll',parameters=None,app_source='laboratorio'):
        from .app_sources import source_profile,require_like_mapping
        source_profile(app_source)
        if action != 'app_prepare':require_like_mapping(app_source)
        if action not in ('lab_like_comment_scroll', 'lab_like', 'lab_like_flow', 'app_prepare'):
            raise ValueError('Acción de tarea no admitida.')
        batch=str(uuid.uuid4())
        tasks=[]
        with self.db() as db:
            for row in rows:
                identifier=str(uuid.uuid4())
                db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,batch,row['id'],row['display_name'],row['port'],row['serial'],action,comment,'En cola','',now(),now()))
                if action in ('lab_like','lab_like_flow'):
                    context=dict(hardware_serial=row.get('hardware_serial'),device_id=row['id'],name=row['display_name'],rack=row.get('rack'),slot=row.get('slot'),port=row['port'],transport=row['serial'],environment='local_lab',app_source=app_source,package=PACKAGE,target='feed' if action=='lab_like_flow' else 'lab_like_01',parameters=parameters)
                    db.execute('INSERT INTO like_context VALUES (?,?)',(identifier,json.dumps(context,ensure_ascii=False,sort_keys=True)))
                tasks.append(dict(id=identifier,row=row,comment=comment,action=action,parameters=parameters,app_source=app_source))
        return tasks

    def update(self,identifier,status,detail=''):
        with self.db() as db:
            db.execute('UPDATE tasks SET status=?,detail=?,updated=? WHERE id=?',(status,detail,now(),identifier))
            row=db.execute('SELECT action FROM tasks WHERE id=?',(identifier,)).fetchone()
            if row and row['action'] in ('lab_like','lab_like_flow'):
                db.execute('INSERT INTO like_events(task_id,at,kind,data) VALUES (?,?,?,?)',(identifier,now(),'task_status',json.dumps(dict(status=status,detail=detail),ensure_ascii=False)))

    def attach_recipe(self,identifiers,recipe):
        spec=json.dumps(recipe,ensure_ascii=False,sort_keys=True)
        digest=hashlib.sha256(spec.encode('utf-8')).hexdigest()
        with self.db() as db:
            db.executemany('INSERT INTO task_recipes VALUES (?,?,?,?)',[(identifier,recipe['id'],spec,digest) for identifier in identifiers])

    def like_event(self, identifier, kind, data):
        if kind not in ('started','observed','click_requested','verified','evidence','scroll'):
            raise ValueError('Tipo de evento no admitido.')
        with self.db() as db:
            if not db.execute('SELECT 1 FROM like_context WHERE task_id=?',(identifier,)).fetchone():
                raise ValueError('Falta contexto auditable; no ejecutar acción.')
            db.execute('INSERT INTO like_events(task_id,at,kind,data) VALUES (?,?,?,?)',(identifier,now(),kind,json.dumps(data,ensure_ascii=False,sort_keys=True)))
        emit('task.event',kind,task_id=identifier,**{k:v for k,v in data.items() if k in ('target','index','outcome','state','moved','can_scroll_more')})

    def like_report(self):
        with self.db() as db:
            rows=[dict(r) for r in db.execute("SELECT t.*,c.context,r.sha256 AS recipe_sha256,r.recipe_id,r.spec AS recipe_spec FROM tasks t LEFT JOIN like_context c ON c.task_id=t.id LEFT JOIN task_recipes r ON r.task_id=t.id WHERE t.action IN ('lab_like','lab_like_flow') ORDER BY t.created,t.rowid")]
            events={}
            for row in db.execute('SELECT * FROM like_events ORDER BY id'):
                item=dict(row);item['data']=json.loads(item['data'])
                events.setdefault(item['task_id'],[]).append(item)
        for row in rows:
            row['recipe_spec']=json.loads(row['recipe_spec']) if row['recipe_spec'] else None
            row['context']=json.loads(row['context']) if row['context'] else None
            row['events']=events.get(row['id'],[])
            verified=[e['data']['outcome'] for e in row['events'] if e['kind']=='verified']
            row['outcome']=verified[-1] if verified else 'unconfirmed' if row['context'] else 'historical_unmeasured'
            row['processed']=any(e['kind']=='started' for e in row['events'])
            units={}
            for e in row['events']:
                if e['kind'] not in ('started','verified'):continue
                target=e['data'].get('target','lab_like_01')
                unit=units.setdefault(target,dict(target=target,processed=False,outcome='unconfirmed'))
                if e['kind']=='started':unit['processed']=True
                if e['kind']=='verified':unit['outcome']=e['data']['outcome']
            row['interactions']=list(units.values())
        return rows

    def like_history(self):
        history=[]
        for task in self.like_report():
            context=task['context'] or {}
            units=task['interactions'] or ([dict(target=None,outcome='historical_unmeasured')] if not context else [])
            for unit in units:
                target=unit['target']
                events=[e for e in task['events'] if e['data'].get('target',context.get('target'))==target]
                verified=[e for e in events if e['kind']=='verified']
                evidence=[e['data'] for e in events if e['kind']=='evidence']
                destination='No disponible'
                if context.get('package') and target:
                    destination=('Granjita Lab · tarjeta '+target.rsplit('_',1)[-1]) if context['package']==PACKAGE and re.fullmatch(r'lab_like_[0-9]{2}',target) else context['package']+' / '+target
                history.append(dict(at=verified[-1]['at'] if verified else events[-1]['at'] if events else task['updated'],
                    device=context.get('name') or task['name'],hardware_serial=context.get('hardware_serial'),
                    destination=destination,package=context.get('package'),target=target,outcome=unit['outcome'],task_id=task['id'],batch=task['batch'],
                    evidence=evidence[-1] if evidence else None))
        return sorted(history,key=lambda row:row['at'],reverse=True)

    def like_metrics(self):
        report=self.like_report()
        units=[u for r in report for u in r['interactions']]
        return dict(scheduled=len(report),processed=sum(u['processed'] for u in units),
            applied=sum(u['outcome']=='applied' for u in units),already_marked=sum(u['outcome']=='already_marked' for u in units),
            unconfirmed=sum(u['outcome']=='unconfirmed' and u['processed'] for u in units),
            historical_unmeasured=sum(r['outcome']=='historical_unmeasured' for r in report))


    def tasks(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT t.*,r.spec AS recipe_spec FROM tasks t LEFT JOIN task_recipes r ON r.task_id=t.id ORDER BY t.created DESC,t.rowid DESC LIMIT 300')]

    def latest_batch_summary(self):
        from .task_results import summarize_batch
        with self.db() as db:
            latest=db.execute('SELECT batch FROM tasks ORDER BY created DESC,rowid DESC LIMIT 1').fetchone()
            if not latest:return None
            rows=[dict(r) for r in db.execute('SELECT t.*,r.spec AS recipe_spec FROM tasks t LEFT JOIN task_recipes r ON r.task_id=t.id WHERE t.batch=? ORDER BY t.rowid',(latest['batch'],))]
        return summarize_batch(rows)
