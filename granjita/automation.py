"""Ejecutor de laboratorio Appium y adaptador explícito de Automate."""
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
        try:
            detail = json.load(exc)['value']['message']
        except Exception:
            detail = f'HTTP {exc.code}'
        raise AutomationError(str(detail)[:3000]) from exc
    value = result.get('value')
    if isinstance(value, dict) and value.get('error'):
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

    def __enter__(self):
        validate_target(self.row)
        if not (DATA/'granjita-lab.apk').is_file():
            raise AutomationError('Falta compilar data/granjita-lab.apk.')
        # noReset omite la actualización de APK en algunas versiones del driver.
        # Actualizar explícitamente SOLO la APK propia y preservar sus datos (-r).
        config=runtime()
        install=subprocess.run([str(Path(config['sdk'])/'platform-tools/adb.exe'),'-P',str(self.row['port']),'-s',self.row['serial'],'install','-r',str(DATA/'granjita-lab.apk')],capture_output=True,text=True,timeout=120,creationflags=0x08000000)
        if install.returncode or 'Success' not in install.stdout:
            raise AutomationError('No se pudo instalar Granjita Lab: '+(install.stdout+install.stderr)[-1500:])
        start_appium()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        result=http('POST','/session',{'capabilities':{'alwaysMatch':capabilities(self.row,port),'firstMatch':[{}]}})
        self.id=result['sessionId']
        return self

    def call(self,method,path,data=None):
        return http(method,f'/session/{self.id}'+path,data)

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


def automate_status(row):
    validate_target(row)
    installed=bool(shell(Adb(row['port']),row['serial'],'pm path com.llamalab.automate'))
    if not installed:
        return 'No instalado. Instala Automate desde Google Play en esta placa.'
    enabled=shell(Adb(row['port']),row['serial'],'settings get secure enabled_accessibility_services')
    return 'Instalado · Accesibilidad ' + ('habilitada' if 'com.llamalab.automate/' in enabled else 'pendiente de habilitar por el usuario si el flujo la necesita')


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
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,batch TEXT NOT NULL,device_id TEXT NOT NULL,name TEXT NOT NULL,
                port INTEGER NOT NULL,serial TEXT NOT NULL,action TEXT NOT NULL,comment TEXT NOT NULL,
                status TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pilot_devices(device_id TEXT PRIMARY KEY);
            ''')
            db.execute("UPDATE tasks SET status='Resultado incierto',detail='La aplicación se cerró durante una tarea. No se reintenta automáticamente.' WHERE status='Ejecutando'")
            db.execute("UPDATE tasks SET status='Interrumpido',detail='Lote interrumpido. Crear un nuevo lote para continuar.' WHERE status='En cola'")

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self,rows,comment):
        batch=str(uuid.uuid4())
        tasks=[]
        with self.db() as db:
            for row in rows:
                identifier=str(uuid.uuid4())
                db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,batch,row['id'],row['display_name'],row['port'],row['serial'],'lab_like_comment_scroll',comment,'En cola','',now(),now()))
                tasks.append(dict(id=identifier,row=row,comment=comment))
        return tasks

    def update(self,identifier,status,detail=''):
        with self.db() as db:
            db.execute('UPDATE tasks SET status=?,detail=?,updated=? WHERE id=?',(status,detail,now(),identifier))

    def tasks(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created DESC,rowid DESC LIMIT 300')]
