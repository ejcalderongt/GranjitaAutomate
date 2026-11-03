"""Configuración de red y proceso de granja controlados desde Streamlit."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from core.database import ROOT


def validar_filas(rows,*,laboratory=False,lab_host=None):
    result=[]
    endpoints=set()
    exits=set()
    for index,row in enumerate(rows,1):
        host=str(row.get('host') or '').strip()
        exit_ip=str(row.get('exit_ip') or '').strip()
        if not host and not exit_ip:
            continue
        try:
            host=str(ipaddress.IPv4Address(host))
            port=int(row['port'])
            if float(row['port'])!=port or not 1<=port<=65535:
                raise ValueError()
            exit_ip=str(ipaddress.IPv4Address(exit_ip))
        except (KeyError,ValueError,TypeError) as exc:
            raise ValueError(f'Fila {index}: completa IPv4 del proxy, puerto 1–65535 e IP de salida.') from exc
        enabled=bool(row.get('enabled',False))
        if laboratory and host!=lab_host:
            raise ValueError(f'Fila {index}: el laboratorio debe usar {lab_host}.')
        if enabled and ((not laboratory and not ipaddress.ip_address(host).is_global) or not ipaddress.ip_address(exit_ip).is_global):
            raise ValueError(f'Fila {index}: sustituye las IPs de ejemplo por IPs públicas reales antes de habilitarla.')
        if (host,port) in endpoints or (enabled and not laboratory and exit_ip in exits):
            raise ValueError(f'Fila {index}: endpoint repetido o IP de salida habilitada duplicada.')
        endpoints.add((host,port))
        if enabled:
            exits.add(exit_ip)
        result.append(dict(host=host,port=port,exit_ip=exit_ip,enabled=enabled))
    return result


def guardar_pool(path,rows):
    path=Path(path)
    metadata=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    laboratory=metadata.get('mode')=='laboratory'
    # La elección de modo es explícita en la configuración; la tabla no lo cambia.
    if metadata.get('mode','production') not in ('production','laboratory'):
        raise ValueError('Modo de red desconocido')
    rows=validar_filas(rows,laboratory=laboratory,lab_host=metadata.get('lab_host'))
    if not rows:
        raise ValueError('Añade al menos un proxy antes de guardar.')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        data={'proxies':rows}
        if laboratory:
            data.update(mode='laboratory',lab_host=metadata['lab_host'])
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return rows


class FarmJobs:
    def __init__(self,root=ROOT):
        self.root=Path(root).resolve()
        self.lock=threading.Lock()
        self.process=None
        self.directory=None

    def start(self,*,smoke,count,cycles,db_path,network_mode='root'):
        from core.project_env import load_project_environment
        load_project_environment(self.root/'.env')
        from core.deployment_check import preparar_pool,fijar_adb_local,seleccionar_proxies_smoke
        if not 1<=count<=40 or cycles<0 or (smoke and cycles==0):
            raise ValueError('Selecciona 1–40 placas y ciclos finitos para el smoke test.')
        if network_mode not in ('root','proxy-laboratory','vpn-lockdown'):
            raise ValueError('Modo de red desconocido')
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError('Ya hay una automatización activa.')
            if os.getenv('PANDA_SIMULATION')=='1':
                raise RuntimeError('El dashboard de simulación no inicia automatizaciones físicas.')
            entries=preparar_pool(self.root/'config/proxy_pool.json',count,required=count if smoke else 1)
            if smoke:
                seleccionar_proxies_smoke(entries,count)
            fijar_adb_local()
            if not os.getenv('OPENAI_API_KEY'):
                raise ValueError('Define OPENAI_API_KEY en el entorno del servidor y reinicia el dashboard.')
            directory=self.root/'sessions/farm_ui'/uuid.uuid4().hex
            directory.mkdir(parents=True)
            command=[sys.executable,'-u',str(self.root/'main.py')]
            command+=['--smoke-test',str(count)] if smoke else ['--start-farm','--devices',str(count)]
            command+=['--cycles',str(cycles),'--stop-file',str(directory/'stop')]
            if network_mode!='root':
                command+=['--network-mode',network_mode]
            environment=os.environ.copy()
            environment['TIKTOK_DB_PATH']=str(db_path)
            environment['PYTHONIOENCODING']='utf-8'
            with (directory/'process.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=self.root,env=environment,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.directory=directory

    def cancel(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                (self.directory/'stop').touch()

    def snapshot(self):
        with self.lock:
            if self.directory is None:
                return None
            result={'returncode':self.process.poll(),'stopping':(self.directory/'stop').exists()}
            path=self.directory/'process.log'
            with path.open('rb') as file:
                file.seek(max(0,path.stat().st_size-16000))
                result['log']=file.read().decode('utf-8',errors='replace')
            return result


class WebJobs(FarmJobs):
    """Proceso web independiente de Streamlit; no comparte Page ni credenciales por CLI."""
    def start_web(self,*,endpoint,profile,cycles,login_only,execute,db_path,username='',password='',selectors=None):
        import importlib.util
        from core.browser import validar_account_id
        from core.database import Database
        from core.web_orchestrator import construir_plan_web
        from config.proxies import leer_proxy_pool
        from core.project_env import load_project_environment
        load_project_environment(self.root/'.env')
        if importlib.util.find_spec('patchright') is None:
            raise ValueError('Instala requirements-web.txt y ejecuta python -m patchright install chromium')
        if not 1<=cycles<=100000:
            raise ValueError('Selecciona al menos un ciclo web')
        profile=validar_account_id(profile)
        database=Database(db_path)
        with database.conexion() as con:
            row=con.execute('SELECT account_id FROM proxy_perfiles WHERE endpoint=?',(endpoint,)).fetchone()
        account=row['account_id'].removeprefix('web:') if row else profile
        accounts=[{'id':account,'profile':profile,'proxy':endpoint}]
        construir_plan_web(accounts,leer_proxy_pool(self.root/'config/proxy_pool.json'))
        selectors=Path(selectors or self.root/'config/web_selectors.mobile.json').resolve()
        if not login_only:
            if not os.getenv('OPENAI_API_KEY'):
                raise ValueError('Falta OPENAI_API_KEY')
            config=json.loads(selectors.read_text(encoding='utf-8-sig'))
            required=['login','authenticated','active_video']+(['comment_close'] if execute else [])
            if any(not config.get(key) or 'REEMPLAZAR' in config[key] for key in required):
                raise ValueError('Valida los selectores web antes de iniciar')
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError('Ya existe una ejecución web activa')
            directory=self.root/'sessions/web_ui'/uuid.uuid4().hex
            directory.mkdir(parents=True)
            config_path=directory/'accounts.json'
            config_path.write_text(json.dumps(accounts),encoding='utf-8')
            command=[sys.executable,'-u',str(self.root/'main.py'),'--web-accounts',str(config_path),
                '--web-engine','patchright','--web-warmup','--cycles',str(cycles),
                '--web-selectors',str(selectors),'--stop-file',str(directory/'stop')]
            if login_only:
                command.append('--web-login-only')
            elif execute:
                command.append('--execute')
            environment=os.environ.copy()
            environment.update(TIKTOK_DB_PATH=str(db_path),PYTHONIOENCODING='utf-8',
                PANDA_WEB_PROXY_USERNAME=username,PANDA_WEB_PROXY_PASSWORD=password)
            with (directory/'process.log').open('wb') as log:
                self.process=subprocess.Popen(command,cwd=self.root,env=environment,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.directory=directory
