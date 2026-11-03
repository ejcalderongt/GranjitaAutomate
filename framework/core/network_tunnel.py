"""Tun2socks del host con contención de fallos nativos; no accede a la TUN Android."""
import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from uuid import uuid4

from core.audit_artifacts import reporte_bloqueado
from core.database import ROOT
from core.source_state import huella_codigo


class TunnelError(RuntimeError):
    pass


def validar_preflight(report_path,*,root=ROOT,apk_path=None):
    report=json.loads(Path(report_path).read_text(encoding='utf-8'))
    expected=report.get('helper_apk_hash','')
    apk=Path(apk_path or Path(root)/'tools/agx_vpn_helper.apk')
    if not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected):
        raise TunnelError('Falta helper_apk_hash SHA-256 válido')
    if not apk.is_file() or hashlib.sha256(apk.read_bytes()).hexdigest()!=expected:
        raise TunnelError('APK ausente o diferente del hash auditado')
    tests=report.get('global_tests',{})
    if tests.get('status')!='passed' or tests.get('exit_code')!=0 or tests.get('source_digest')!=huella_codigo(root):
        raise TunnelError('Ejecutar la suite global sobre el código actual antes de iniciar el motor')
    return report


def _registrar(report_path,run_id,state,**details):
    with reporte_bloqueado(report_path) as report:
        if state!='iniciando' and report.get('motor_tcp_run_id') not in (None,run_id):
            return
        report.update(motor_tcp_run_id=run_id,motor_tcp_estado=state,
            motor_tcp_scope='host_windows',motor_tcp_android_deployment_ready=False,
            motor_tcp_detalle=details)


def _rest_ready(address):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://'+address+'/netstats',timeout=.5) as response:
            return response.status==200 and isinstance(json.loads(response.read(200000)),dict)
    except (OSError,ValueError):
        return False


def _interfaz(device):
    try:
        return any(name==device for _,name in socket.if_nameindex())
    except OSError:
        return False


class MotorTunel:
    def __init__(self,process,folder,report,run_id,options,timeout,ready_probe):
        self.process,self.folder,self.report,self.run_id=process,folder,report,run_id
        self.options,self.timeout,self.ready_probe=options,timeout,ready_probe
        self.estado='iniciando'
        self.finalizado=threading.Event()
        self._stop=threading.Event()
        self.monitor=threading.Thread(target=self._monitor,name='agx-tun-monitor',daemon=True)
        self.monitor.start()

    def _update(self,state,**details):
        self.estado=state
        with reporte_bloqueado(self.folder/'status.json') as data:
            data.update(state=state,run_id=self.run_id,scope='host_windows',android_deployment_ready=False,**details)
        try:
            _registrar(self.report,self.run_id,state,log=str(self.folder/'motor.log'),**details)
        except (OSError,ValueError):
            print('[Túnel] Reporte global no actualizado; estado conservado en el directorio del motor.',flush=True)

    def _terminate(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def _monitor(self):
        deadline=time.monotonic()+self.timeout
        active=False
        try:
            while not self._stop.wait(.2):
                code=self.process.poll()
                if code is not None:
                    text=(self.folder/'motor.log').read_text(encoding='utf-8',errors='replace')[-1800:]
                    self._update('fallido',exit_code=code,error='El motor nativo terminó',native_log_tail=text)
                    print('[Túnel] Proceso nativo finalizado; revisar '+str(self.folder/'motor.log'),flush=True)
                    return
                if not active and _rest_ready(self.options['restAPI']) and _interfaz(self.options['device']):
                    if self.ready_probe is not None and self.ready_probe() is True:
                        active=True
                        self._update('activo',verification='REST + interfaz del host + prueba de datos del host')
                        self.finalizado.set()
                    elif self.estado!='iniciado_sin_validar_datos':
                        self._update('iniciado_sin_validar_datos',verification='REST e interfaz; sin prueba de datos por TUN')
                if not active and time.monotonic()>=deadline:
                    self._terminate()
                    self._update('fallido',error='No se confirmó transporte por la TUN en el plazo indicado',
                                 host_interface_cleanup_requires_verification=True)
                    return
        except Exception as exc:
            self._terminate()
            self._update('fallido',error_type=type(exc).__name__,host_interface_cleanup_requires_verification=True)
        finally:
            self.finalizado.set()

    def cerrar(self):
        self._stop.set()
        self._terminate()
        self.monitor.join(timeout=6)
        self._update('detenido',host_interface_cleanup_requires_verification=True)
        # La API publicada no expone Stop; no anunciar restauración de rutas/DNS.


def iniciar_motor_tunel_tcp(device='tun0',networkInterface='any',logLevel='info',
                           proxy='http://127.0.0.1:8080',restAPI='127.0.0.1:6060',*,
                           report_path=None,scope='host',startup_timeout=5,ready_probe=None):
    report_path=Path(report_path or ROOT/'runs/resultado_global.json').resolve()
    run_id=uuid4().hex
    try:
        validar_preflight(report_path)
        if scope!='host':
            raise TunnelError('Un proceso Windows no puede abrir la TUN de VpnService Android; integrar un motor dentro del APK')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',device) or not .5<=startup_timeout<=30:
            raise TunnelError('Interfaz o timeout inválido')
        if logLevel not in ('debug','info','warn','error','silent'):
            raise TunnelError('Nivel de log inválido')
        parsed=urlsplit(proxy)
        if parsed.scheme not in ('http','https') or not parsed.hostname or not parsed.port or parsed.username or parsed.password:
            raise TunnelError('Proxy HTTP requiere endpoint sin credenciales en URL')
        rest=urlsplit('//'+restAPI)
        if rest.hostname!='127.0.0.1' or not rest.port or not 1<=rest.port<=65535:
            raise TunnelError('La API REST debe escuchar en 127.0.0.1:puerto')
        with socket.socket() as check:
            check.bind((rest.hostname,rest.port))
        if networkInterface!='any' and networkInterface not in ('',*[name for _,name in socket.if_nameindex()]):
            raise TunnelError('Interfaz física del host inexistente')
        if importlib.util.find_spec('tun2socks') is None:
            raise TunnelError('Instalar el binding con scripts/preparar_tun2socks.py')
        options=dict(device=device,networkInterface='' if networkInterface=='any' else networkInterface,
                     logLevel=logLevel,proxy=proxy,restAPI=restAPI)
        folder=ROOT/'runs'/('motor-tcp-'+run_id);folder.mkdir(parents=True)
        config=folder/'options.json';config.write_text(json.dumps(options),encoding='utf-8')
        _registrar(report_path,run_id,'iniciando',options=options,log=str(folder/'motor.log'))
        with (folder/'motor.log').open('wb') as log:
            process=subprocess.Popen([sys.executable,'-u','-m','core.network_tunnel','--worker',str(config)],
                cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        return MotorTunel(process,folder,report_path,run_id,options,startup_timeout,ready_probe)
    except Exception as exc:
        try:
            _registrar(report_path,run_id,'iniciando',scope_requested=scope)
            _registrar(report_path,run_id,'bloqueado',error_type=type(exc).__name__,error=str(exc))
        except (OSError,ValueError):
            print('[Túnel] Se conserva el reporte original que no pudo actualizarse.',flush=True)
        print('[Túnel] Inicio bloqueado: '+str(exc),flush=True)
        raise TunnelError(str(exc)) from exc


def _worker(path):
    import tun2socks
    options=json.loads(Path(path).read_text(encoding='utf-8'))
    errors=[]
    def run():
        try:
            tun2socks.startFromArgs(options['device'],options['networkInterface'],options['logLevel'],
                                   options['proxy'],options['restAPI'])
        except Exception as exc:
            errors.append(type(exc).__name__)
            print('[Túnel] Excepción del binding: '+type(exc).__name__,flush=True)
    thread=threading.Thread(target=run,name='agx-tun-native',daemon=True)
    thread.start()
    thread.join()
    return 2 if errors else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=Path,required=True)
    raise SystemExit(_worker(parser.parse_args().worker))
