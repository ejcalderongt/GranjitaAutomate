"""Granja ADB: rutas fijadas, procesos acotados, inventario WAL y cierre cooperativo."""
import ipaddress
import json
import multiprocessing as mp
import os
import signal
import sys
import time
import traceback
import uuid
import random
import sqlite3
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone

from openai import OpenAI
from config.proxies import ADBError,adb,usar_servidor_adb,configurar_proxy_dispositivo,limpiar_proxy_dispositivo
from config.proxies import ProxyAllocator,leer_proxy_pool
from config.device_test import shell,consultar_ip
from config.network_guard import trafico_restringido,recuperar_firewall
from core.adb_pool import cargar_servidores,descubrir_pool,cargar_objetivos
from core.ai_orchestrator import ejecutar_feed
from core.database import Database,ROOT
from core.diagnostic_bridge import escribir_json
from core.selectors import esperar_feed,comprobar_cuenta
from config.android_app import TIKTOK_PACKAGE, validar_componente_instalado
from core.panda_identity import resolver_pool_panda, confirmar_identidad
from core.bootstrap import preparar_pantalla, recuperar_placa, recuperar_sesiones
from core.runtime_health import ClienteRecuperable, liberar_api, ParadaRecuperable


class FarmStopped(RuntimeError):
    pass


class CuentaPendiente(RuntimeError):
    pass


def clave_placa(item):
    return item.get('device_id',item['route'].serial)


def seleccionar_subset(snapshot,count):
    ready=sorted(serial for serial,route in snapshot.devices.items()
                 if route.status=='device' and not serial.startswith('emulator-'))
    if count is None:
        return set(ready)
    if not 1<=count<=40 or len(ready)<count:
        raise ValueError(f'Smoke test requiere {count} placas autorizadas; solo hay {len(ready)}')
    return set(ready[:count])


def startup_delay():
    return random.SystemRandom().uniform(2,5)


@contextmanager
def bloquear_granja(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0); file.write(b'0'); file.flush(); file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Ya existe un orquestador de granja activo en este workspace') from exc
        yield


class ClienteLimitado:
    def __init__(self,client,gate,lock,next_request,stop,rpm):
        self.client,self.gate,self.lock=client,gate,lock
        self.next_request,self.stop,self.rpm=next_request,stop,rpm
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self,**kwargs):
        while not self.stop.is_set():
            if self.gate.acquire(timeout=.5):
                break
        else:
            raise FarmStopped()
        try:
            with self.lock:
                slot=max(time.monotonic(),self.next_request.value)
                self.next_request.value=slot+60/self.rpm
            if self.stop.wait(max(0,slot-time.monotonic())):
                raise FarmStopped()
            return self.client.chat.completions.create(**kwargs)
        finally:
            self.gate.release()


def cargar_proxies(path):
    result=[]
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        host,port=line.strip().rsplit(':',1)
        host=str(ipaddress.IPv4Address(host))
        port=int(port)
        if not 1<=port<=65535:
            raise ValueError('Puerto proxy fuera de rango')
        result.append((host,port))
    if len(set(result))!=len(result):
        raise ValueError('Cada placa requiere un endpoint proxy único')
    return result


def cleanup_worker(item,package):
    directory=Path(item['directory'])
    if not any((directory/name).exists() for name in ('proxy_lease.json','firewall_lease.json','vpn_lease.json')):
        return None
    server=item['route'].server
    with usar_servidor_adb(server.host,server.port):
        try:
            confirmar_identidad(item['route'])
            # Nunca retirar el firewall con TikTok ejecutándose tras un cierre forzado.
            shell(item['route'].serial,'am','force-stop',package)
            if (directory/'vpn_lease.json').exists():
                from core.network_lockdown import liberar_lockdown_dispositivo
                liberar_lockdown_dispositivo(item['route'].serial,sessions=directory)
            recuperar_firewall(item['route'].serial,directory)
            if (directory/'proxy_lease.json').exists():
                lease=json.loads((directory/'proxy_lease.json').read_text(encoding='utf-8'))
                if lease.get('mode')=='proxy_laboratory':
                    from core.network_isolation import restaurar_red_dispositivo
                    restaurar_red_dispositivo(item['route'].serial,sessions=directory)
                else:
                    limpiar_proxy_dispositivo(item['route'].serial)
                    (directory/'proxy_lease.json').unlink()
            (directory/'cleanup_required.json').unlink(missing_ok=True)
            return None
        except Exception as exc:
            escribir_json(directory/'cleanup_required.json',{
                'serial':item['route'].serial,'adb_host':server.host,'adb_port':server.port,
                'error':str(exc),'directory':str(directory)})
            return str(exc)


def farm_worker(item,args,stop,gate,rate_lock,next_request,db_path):
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    route=item['route']
    device_id=clave_placa(item)
    directory=Path(item['directory'])
    directory.mkdir(parents=True,exist_ok=True)
    exitcode=0
    client=None
    retryable=False
    work_completed=False
    token=item.get('worker_token',f"{item.get('reservation_owner','')}:{device_id}:{os.getpid()}")
    pending_account=False
    ip=None
    network_ready=False
    with (directory/'worker.log').open('a',encoding='utf-8',buffering=1) as log:
        with redirect_stdout(log),redirect_stderr(log),usar_servidor_adb(route.server.host,route.server.port):
            db=Database(db_path)
            allocator=ProxyAllocator(db)
            owner=item.get('reservation_owner')
            smoke=bool(getattr(args,'smoke_test',None))
            def emit(message,*,level='INFO',**details):
                details.update(alias=item.get('alias'),legacy_device_id=item.get('legacy_device_id'),
                               adb_transport=route.serial,device_id=device_id)
                print(message,details,flush=True)
                if owner:
                    db.log_granja(owner,device_id,message,nivel=level,detalle=details)
                db.marcar_latido(device_id)
            try:
                if stop.is_set():
                    raise FarmStopped()
                if item.get('reservation_owner') and not allocator.validar(device_id,
                    item['reservation_owner'],f"{item['proxy'][0]}:{item['proxy'][1]}"):
                    raise RuntimeError('Reserva de proxy ausente o propiedad de otro worker')
                db.actualizar_dispositivo(device_id,proxy=f"{item['proxy'][0]}:{item['proxy'][1]}",
                                          estado='Calentando',conectado=True)
                if adb('-s',route.serial,'get-state')!='device':
                    raise ADBError('Dispositivo no disponible en su servidor de origen')
                if smoke and shell(route.serial,'getprop','ro.kernel.qemu').strip()=='1':
                    raise ADBError('El smoke test físico no admite un emulador')
                if smoke:
                    if ':' in route.serial:
                        if not route.hardware_serial or device_id!=route.hardware_serial:
                            raise ADBError('TCP Panda requiere identidad física verificada antes del arranque')
                        confirmar_identidad(route)
                    elif not adb('-s',route.serial,'get-devpath').startswith('usb:'):
                        raise ADBError('El smoke test requiere USB o TCP Panda verificado')
                preparar_pantalla(route,command=shell)
                emit('Worker iniciado',server=route.server.key)
                if args.package==TIKTOK_PACKAGE:
                    validar_componente_instalado(route.serial,args.package,args.activity)
                shell(route.serial,'am','force-stop',args.package)
                laboratory_mode=getattr(args,'network_mode','root')=='proxy-laboratory'
                vpn_mode=getattr(args,'network_mode','root')=='vpn-lockdown'
                scope='Android: HTTPS explícito bajo firewall; no acredita tráfico TikTok'
                if vpn_mode:
                    from core.network_lockdown import lockdown_vpn,SCOPE
                    guard=lockdown_vpn(route.serial,*item['proxy'],sessions=directory)
                    scope=SCOPE
                elif laboratory_mode:
                    if not item.get('laboratory'):
                        raise ValueError('El modo sin root solo admite un pool marcado laboratory')
                    from core.network_isolation import proxy_laboratorio_sin_root,SCOPE
                    guard=proxy_laboratorio_sin_root(route.serial,*item['proxy'],sessions=directory)
                    scope=SCOPE
                else:
                    escribir_json(directory/'proxy_lease.json',{
                        'serial':route.serial,'server':route.server.key,'proxy':item['proxy'],
                        'reservation_owner':item.get('reservation_owner')})
                    configurar_proxy_dispositivo(route.serial,*item['proxy'])
                    emit('Proxy Android verificado')
                    guard=trafico_restringido(route.serial,*item['proxy'],sessions=directory,preserve_management=True)
                with guard as verify:
                    try:
                        emit('VPN configurada y estado del helper verificado' if vpn_mode else
                             'Proxy de laboratorio sin root activo; salida directa WiFi no bloqueada' if laboratory_mode
                             else 'Firewall activo; verificando salida HTTPS',scope=scope)
                        def observar_salida():
                            if vpn_mode:
                                return verify.public_ip()
                            endpoint=f"{item['proxy'][0]}:{item['proxy'][1]}"
                            if item.get('laboratory'):
                                return consultar_ip(route.serial,endpoint,allow_native=True)
                            return consultar_ip(route.serial,endpoint)
                        if owner:
                            from core.network_audit import verificar_proxy_auditable
                            observed=[None]
                            def before_confirm(value):
                                observed[0]=value
                                db.registrar_ip(owner,device_id,value,smoke=smoke,laboratory=item.get('laboratory',False))
                            try:
                                ip=verificar_proxy_auditable(db,allocator,owner,device_id,
                                    f"{item['proxy'][0]}:{item['proxy'][1]}",
                                    leer_configuracion=lambda:verify.endpoint() if vpn_mode else shell(route.serial,'settings','get','global','http_proxy'),
                                    consultar_salida=observar_salida,expected_ip=item.get('expected_exit_ip'),
                                    before_confirm=before_confirm,alcance=scope)
                                db.registrar_ip(owner,device_id,ip,smoke=smoke,confirmada=True,laboratory=item.get('laboratory',False))
                            except (ValueError,sqlite3.IntegrityError) as exc:
                                if observed[0] is not None:
                                    db.registrar_ip(owner,device_id,observed[0],smoke=smoke,error=str(exc),laboratory=item.get('laboratory',False))
                                    emit('Verificación de IP rechazada; abortando',level='CRITICAL',ip=observed[0],error=str(exc))
                                    stop.set()
                                raise
                        else:
                            ip=observar_salida()
                        network_ready=True
                        emit('IP externa confirmada',ip=ip)
                        escribir_json(directory/'egress.json',{'observed_ip':ip,
                            'scope':scope})
                        if stop.is_set():
                            raise FarmStopped()
                        result=shell(route.serial,'am','start','-W','-n',f'{args.package}/{args.activity}')
                        if 'Status: ok' not in result or 'Error' in result or 'Exception' in result:
                            raise ADBError(f'No se confirmó el arranque: {result[:300]}')
                        last_check=[0.0]
                        last_proxy_check=[time.monotonic()]
                        def check():
                            if stop.is_set():
                                raise FarmStopped()
                            now=time.monotonic()
                            if now-last_check[0]>=5:
                                if adb('-s',route.serial,'get-state')!='device':
                                    raise ADBError('Se perdió el dispositivo en su servidor ADB')
                                confirmar_identidad(route)
                                if getattr(args,'auto_heal',False):
                                    expected_proxy=f"{item['proxy'][0]}:{item['proxy'][1]}"
                                    if not vpn_mode and shell(route.serial,'settings','get','global','http_proxy')!=expected_proxy:
                                        if owner:
                                            db.auditar_proxy(owner,device_id,expected_proxy,'supervision','fallido',
                                                error_tipo='ConfiguracionPerdida')
                                        raise ADBError('La placa perdió la configuración del proxy')
                                    if now-last_proxy_check[0]>=30:
                                        observed=(verificar_proxy_auditable(db,allocator,owner,device_id,expected_proxy,
                                            leer_configuracion=lambda:verify.endpoint() if vpn_mode else shell(route.serial,'settings','get','global','http_proxy'),
                                            consultar_salida=observar_salida,expected_ip=ip,alcance=scope) if owner else observar_salida())
                                        if observed!=ip:
                                            raise ADBError('El proxy perdió la salida verificada')
                                        last_proxy_check[0]=now
                                verify()
                                last_check[0]=now
                        markers=None
                        if getattr(args,'feed_markers',None):
                            markers=json.loads(Path(args.feed_markers).read_text(encoding='utf-8'))['markers']
                        def auth_check(strict):
                            result=comprobar_cuenta(route.serial,args.package,sessions=directory,
                                                   strict_profile=strict)
                            if result['authenticated'] is False:
                                db.registrar_auth(device_id,False,result['reason'])
                                emit('Pendiente Cuenta',level='WARNING',reason=result['reason'])
                                raise CuentaPendiente(result['reason'])
                            if strict and result['authenticated'] is True:
                                db.registrar_auth(device_id,True,result['reason'])
                                emit('Auth Check: UI compatible con cuenta')
                        def auth_progress(data):
                            emit('Micro-dumps de interfaz',**data)
                            if data.get('state')=='login_required':
                                db.registrar_auth(device_id,False,data['reason'])
                                emit('Pendiente Cuenta',level='WARNING',reason=data['reason'])
                                raise CuentaPendiente(data['reason'])
                        def wait_for_ui():
                            load_started=time.perf_counter()
                            def slow():
                                db.actualizar_dispositivo(device_id,estado='Carga Lenta - Reintentando')
                                emit('Carga Lenta - Reintentando',level='WARNING')
                            for window in range(getattr(args,'max_failures',5)):
                                check()
                                emit('Espera Dinámica',window=window+1)
                                try:
                                    result=esperar_feed(route.serial,args.package,stop=stop,markers=markers,
                                        on_slow=slow,on_progress=auth_progress)
                                except InterruptedError:
                                    raise FarmStopped()
                                if result['ready']:
                                    auth_check(True)
                                    emit('Latencia de carga UI',latencia_ms=round((time.perf_counter()-load_started)*1000,2),
                                         scope='UI lista y auth compatible; reproducción no acreditada')
                                    db.actualizar_dispositivo(device_id,estado='Navegando',conectado=True)
                                    return
                                # Un login visible puede impedir que exista el reproductor.
                                # En carga incompleta no inferir falta de cuenta solo por ausencia de Perfil.
                                auth_check(False)
                                print('Carga Lenta - Reintentando',result,flush=True)
                            raise ADBError('El feed no apareció tras las ventanas de espera dinámica')
                        wait_for_ui()
                        client=OpenAI(timeout=25,max_retries=2)
                        limited=(ClienteRecuperable(client,db,token,owner,device_id,stop,args.rpm,args.api_concurrency)
                                 if getattr(args,'auto_heal',False) else
                                 ClienteLimitado(client,gate,rate_lock,next_request,stop,args.rpm))
                        remaining=args.cycles
                        while not stop.is_set() and (remaining>0 or args.cycles==0):
                            batch=min(20,remaining) if args.cycles else 20
                            ejecutar_feed(route.serial,package=args.package,videos=batch,
                                directory=directory,check=check,client=limited,database=db,database_device_id=device_id,
                                proxy=f"{item['proxy'][0]}:{item['proxy'][1]}",wait_for_ui=wait_for_ui)
                            remaining-=batch
                        work_completed=not stop.is_set() and args.cycles>0 and remaining<=0
                    finally:
                        confirmar_identidad(route)
                        shell(route.serial,'am','force-stop',args.package)
            except (FarmStopped,InterruptedError):
                emit('Parada cooperativa solicitada')
            except CuentaPendiente:
                pending_account=True
                # Es cuarentena operativa de esta placa, no un fallo global de la granja.
                escribir_json(directory/'pending_account.json',{'serial':route.serial,'status':'Pendiente Cuenta'})
            except BaseException as exc:
                exitcode=1
                if owner and not network_ready:
                    db.auditar_proxy(owner,device_id,f"{item['proxy'][0]}:{item['proxy'][1]}",
                        'preparacion','fallido',error_tipo=type(exc).__name__)
                retryable=isinstance(exc,ADBError)
                traceback.print_exc()
            finally:
                if client:
                    try:
                        client.close()
                    except Exception:
                        traceback.print_exc()
                error=cleanup_worker(item,args.package)
                if pending_account and error is None and owner:
                    # Retirar el claim histórico ANTES de hacer el proxy reutilizable.
                    db.excluir_ip_sin_cuenta(owner,device_id)
                if item.get('reservation_owner'):
                    if smoke and error is None and not pending_account:
                        allocator.retener_smoke(device_id,owner)
                    else:
                        allocator.finalizar(device_id,owner,cleanup_ok=error is None)
                if error:
                    exitcode=1
                    retryable=True
                liberar_api(db,token)
                escribir_json(directory/'worker_exit.json',{'retryable':retryable,'work_completed':work_completed,
                              'exitcode':exitcode})
                db.actualizar_dispositivo(device_id,estado='Pendiente Cuenta' if pending_account
                                          else ('Error' if exitcode else 'Espera'))
                emit('Limpieza completada' if error is None else 'Limpieza pendiente',
                     level='INFO' if error is None else 'CRITICAL',exitcode=exitcode)
    raise SystemExit(exitcode)


def pendientes_disponibles(pending,active,limit):
    """Extraer únicamente los slots disponibles; un serial no puede ejecutarse dos veces."""
    result=[]
    while pending and len(active)+len(result)<limit:
        result.append(pending.popleft())
    return result


def reintento_seguro(item):
    """No repetir acciones cuyo resultado externo puede haber sido ambiguo."""
    audit=Path(item['directory'])/'audit.jsonl'
    try:
        if audit.exists():
            with audit.open(encoding='utf-8') as file:
                for line in file:
                    if json.loads(line).get('event') in ('like_attempt','comment_send_attempt'):
                        return False
        outcome=Path(item['directory'])/'worker_exit.json'
        return not outcome.exists() or json.loads(outcome.read_text(encoding='utf-8')).get('retryable',False)
    except (OSError,ValueError):
        return False


def iniciar_granja(args):
    if args.plan:
        return _iniciar_granja(args)
    with bloquear_granja(ROOT/'sessions'/'farm.lock'):
        return _iniciar_granja(args)


def _iniciar_granja(args):
    servers=cargar_servidores(args.adb_servers)
    db=Database()
    db.guardar_servidores(servers)
    started=time.perf_counter()
    targets=cargar_objetivos(servers,args.adb_servers)
    target_count=len({address for addresses in targets.values() for address in addresses})
    expected=getattr(args,'smoke_test',None) or min(args.devices,target_count or 1)
    deadline=started+getattr(args,'bootstrap_timeout',30)
    while True:
        if getattr(args,'stop_file',None) and args.stop_file.exists():
            raise InterruptedError('Arranque cancelado desde el dashboard')
        raw=descubrir_pool(servers,timeout=1.25,reconnect=not args.plan,
                          connect_workers=getattr(args,'bootstrap_parallelism',40),initialize_servers=not args.plan)
        network_ms=round((time.perf_counter()-started)*1000,2)
        initial=resolver_pool_panda(raw,db)
        count=sum(r.status=='device' for r in initial.devices.values())
        db.sincronizar_pool(initial)
        if args.plan or count>=expected or time.perf_counter()>=deadline:
            db.alerta('bootstrap_wait',f'Bootstrap: {count}/{expected} identidades disponibles',activa=count<expected)
            break
        db.alerta('bootstrap_wait',f'Esperando encendido de placas: {count}/{expected}')
        time.sleep(.5)
    db.log_granja('bootstrap',None,'Bootstrap ADB',detalle={'network_ms':network_ms,
        'total_ms':round((time.perf_counter()-started)*1000,2),'connected':sum(r.status=='device' for r in initial.devices.values()),
        'server_errors':raw.errors,'identity_errors':initial.identity_errors,'reconnect_errors':raw.reconnect_errors})
    db.sincronizar_pool(initial)
    ready=[r for r in initial.devices.values() if r.status=='device']
    smoke_count=getattr(args,'smoke_test',None)
    selected=seleccionar_subset(initial,smoke_count)
    print(f'Inventario: {len(initial.devices)} únicos, {len(ready)} autorizados, '
          f'{len(initial.successful)} servidores disponibles. Máximo concurrente: {args.devices}.',
          file=sys.stderr if args.plan else sys.stdout,flush=True)
    if args.plan:
        print(json.dumps({'devices':[{'serial':r.serial,'server':r.server.key,'status':r.status,
                    'origins':[s.key for s in r.origins]} for r in initial.devices.values()],
                    'selected':sorted(selected),'smoke':smoke_count is not None,'identity_errors':initial.identity_errors,
                    'errors':initial.errors},ensure_ascii=False,indent=2))
        return 0
    if not ready:
        raise ADBError('Ningún dispositivo autorizado respondió en el pool configurado')
    recuperar_sesiones(ROOT/'sessions',args,db,cleanup_worker,getattr(args,'bootstrap_parallelism',40))
    from core.deployment_check import verificar_despliegue
    try:
        verificar_despliegue(args)
        if not os.getenv('OPENAI_API_KEY'):
            raise ValueError('Define OPENAI_API_KEY antes de iniciar los workers')
    except (ValueError,OSError,ADBError) as exc:
        db.alerta('deployment',str(exc))
        raise
    db.alerta('deployment','Preflight de workers válido',activa=False)
    if getattr(args,'stop_file',None) and args.stop_file.exists():
        return 130
    proxies=leer_proxy_pool(getattr(args,'proxy_pool',ROOT/'config/proxy_pool.json'))
    if smoke_count:
        from core.deployment_check import seleccionar_proxies_smoke
        proxies=seleccionar_proxies_smoke(proxies,smoke_count)
        print(f'\033[1;96m🚀 INICIANDO SMOKE TEST EN {smoke_count} PLACAS FÍSICAS - RED INYECTADA POR IPABLES\033[0m',flush=True)
    return ejecutar_plan_granja(args,servers,initial,proxies,db)


def ejecutar_plan_granja(args,servers,initial,proxies,db):
    ctx=mp.get_context('spawn')
    stop=(ParadaRecuperable(ctx) if getattr(args,'auto_heal',False) and hasattr(ctx,'RawValue') else ctx.Event())
    gate=ctx.BoundedSemaphore(args.api_concurrency)
    lock,next_request=ctx.Lock(),ctx.Value('d',0)
    run_dir=ROOT/'sessions'/'farm'/uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    allocator=ProxyAllocator(db)
    # Compatibilidad con planes internos antiguos y sus pruebas; el comando usa JSON.
    entries=[{'endpoint':f'{p[0]}:{p[1]}','host':p[0],'port':p[1],'enabled':True}
             if isinstance(p,tuple) else p for p in proxies]
    allocator.sincronizar(entries)
    owner=run_dir.name
    smoke=bool(getattr(args,'smoke_test',None))
    selected=seleccionar_subset(initial,getattr(args,'smoke_test',None)) if smoke else None
    fixed_proxies={serial:entries[i]['endpoint'] for i,serial in enumerate(sorted(selected))} if smoke else {}
    db.iniciar_ejecucion(owner,selected or set(initial.devices),smoke=smoke)
    pending,active,known,started=deque(),{},set(),[]
    failures=[]
    healing={}
    heal_pool=ThreadPoolExecutor(max_workers=getattr(args,'bootstrap_parallelism',8))
    auto_heal=getattr(args,'auto_heal',False)
    def enqueue(snapshot):
        for serial,route in sorted(snapshot.devices.items()):
            if route.status!='device' or serial in known:
                continue
            if selected is not None and serial not in selected:
                continue
            index=len(known)
            item={'route':route,'device_id':serial,'directory':str(run_dir/f'device-{index:03d}'),'reservation_owner':owner}
            identity=db.identidad_agx(serial)
            item.update(alias=identity.get('alias') or serial,
                        legacy_device_id=identity.get('canonical_id'))
            if identity.get('alias'):
                db.actualizar_dispositivo(serial,alias=identity['alias'])
            known.add(serial)
            pending.append(item)
            db.log_granja(owner,serial,'En cola de smoke test' if smoke else 'En cola de granja',
                          detalle={'alias':item['alias'],'legacy_device_id':item['legacy_device_id']})
    enqueue(initial)
    def actualizar_recursos():
        free=allocator.disponibles()
        shortage=max(0,len(pending)-free)
        waiting.clear()
        if shortage:
            waiting.update(clave_placa(i) for i in list(pending)[-shortage:])
        for item in pending:
            serial=clave_placa(item)
            db.actualizar_dispositivo(serial,estado='Espera - Sin Proxy' if serial in waiting else 'Espera')
        db.alerta('network_resources',f'Falta de recursos de red: {shortage} placas esperando proxy único',activa=shortage>0)
    def detener(signum,frame):
        stop.set()
    previous={sig:signal.signal(sig,detener) for sig in (signal.SIGINT,signal.SIGTERM)}
    next_poll,next_start=0.0,0.0
    waiting=set()
    try:
        while (pending or active or healing) and not stop.is_set():
            if getattr(args,'stop_file',None) and args.stop_file.exists():
                stop.set()
                break
            now=time.monotonic()
            if now>=next_poll:
                snapshot=resolver_pool_panda(descubrir_pool(servers,reconnect=True),db)
                db.alerta('panda_identity',f'{len(snapshot.identity_errors)} rutas Panda con identidad no verificada',
                          activa=bool(snapshot.identity_errors))
                db.alerta('panda_reconnect',f'{len(snapshot.reconnect_errors)} conexiones TCP pendientes',
                          activa=bool(snapshot.reconnect_errors))
                db.sincronizar_pool(snapshot)
                if getattr(args,'proxy_pool',None) and not smoke:
                    try:
                        allocator.sincronizar(leer_proxy_pool(args.proxy_pool))
                        db.alerta('proxy_config','Configuración del pool de proxies inválida',activa=False)
                    except (ValueError,KeyError,OSError) as exc:
                        db.alerta('proxy_config',f'Configuración del pool de proxies inválida: {type(exc).__name__}')
                enqueue(snapshot)
                actualizar_recursos()
                escribir_json(run_dir/'inventory.json',{'unique':len(snapshot.devices),
                    'ready':sum(r.status=='device' for r in snapshot.devices.values()),'errors':snapshot.errors})
                next_poll=now+5
            for serial,(future,item,retry) in list(healing.items()):
                if not future.done():
                    continue
                try:
                    error=future.result()
                except Exception as exc:
                    error=str(exc)
                del healing[serial]
                if error is None:
                    item['healed']=True
                    (Path(item['directory'])/'supervisor_lease.json').unlink(missing_ok=True)
                    if retry and item.get('heal_attempt',0)<getattr(args,'auto_heal_attempts',2):
                        replacement=dict(item)
                        replacement['heal_attempt']=item.get('heal_attempt',0)+1
                        replacement['directory']=str(run_dir/f"device-retry-{uuid.uuid4().hex}")
                        replacement.pop('healed',None)
                        pending.append(replacement)
                        db.log_granja(owner,serial,'Worker reencolado tras auto-heal')
                    elif retry:
                        failures.append(serial)
                        item['terminal_failure']=True
                        db.actualizar_dispositivo(serial,estado='Error')
                else:
                    failures.append(serial)
            heartbeat={r['id_adb']:r.get('ultimo_heartbeat') for r in db.dispositivos()} if auto_heal else {}
            for serial,(process,item) in list(active.items()):
                if auto_heal and process.is_alive():
                    last=item.get('started_at',time.time())
                    if heartbeat.get(serial):
                        try:
                            last=max(last,datetime.fromisoformat(heartbeat[serial]).timestamp())
                        except ValueError:
                            pass
                    if time.time()-last>getattr(args,'worker_timeout',180):
                        db.log_granja(owner,serial,'Watchdog: worker sin heartbeat',nivel='WARNING')
                        process.terminate()
                        process.join(1)
                        if process.is_alive() and hasattr(process,'kill'):
                            process.kill()
                            process.join(1)
                if not process.is_alive():
                    process.join()
                    if process.exitcode:
                        if auto_heal:
                            liberar_api(db,item.get('worker_token',''))
                            allocator.finalizar(serial,owner,cleanup_ok=False)
                            retry=reintento_seguro(item)
                            # La limpieza puede ser lo único pendiente de un ciclo ya terminado.
                            outcome=Path(item['directory'])/'worker_exit.json'
                            completed=False
                            if outcome.exists():
                                try:
                                    completed=json.loads(outcome.read_text(encoding='utf-8')).get('work_completed',False)
                                except ValueError:
                                    pass
                            healing[serial]=(heal_pool.submit(recuperar_placa,item,args,db,cleanup_worker),item,retry and not completed)
                            if not retry and not completed:
                                failures.append(serial)
                                item['terminal_failure']=True
                            del active[serial]
                            continue
                        failures.append(serial)
                        stop.set()
                    evidence=Path(item['directory'])
                    error=(cleanup_worker(item,args.package) if any((evidence/name).exists()
                        for name in ('proxy_lease.json','firewall_lease.json','vpn_lease.json')) else None)
                    if error is None:
                        db.excluir_ip_sin_cuenta(owner,serial)
                    if smoke and error is None:
                        allocator.retener_smoke(serial,owner)
                    else:
                        allocator.finalizar(serial,owner,cleanup_ok=error is None)
                    del active[serial]
            if stop.is_set():
                break
            if now>=next_start:
                slots=pendientes_disponibles(pending,active,args.devices)
                parallel=getattr(args,'bootstrap_parallelism',1)
                if len(slots)>parallel:
                    pending.extendleft(reversed(slots[parallel:]))
                    slots=slots[:parallel]
                for item in slots:
                    route=item['route']
                    device_id=clave_placa(item)
                    reservation=(allocator.reservar(device_id,owner,endpoint=fixed_proxies[device_id])
                                 if smoke else allocator.reservar(device_id,owner))
                    if reservation is None:
                        if device_id not in waiting:
                            db.auditar_proxy(owner,device_id,fixed_proxies.get(device_id) if smoke else None,
                                'asignacion','sin_recurso')
                        waiting.add(device_id)
                        db.actualizar_dispositivo(device_id,estado='Espera - Sin Proxy')
                        db.alerta('network_resources','Falta de recursos de red: placas en espera de proxy único')
                        pending.append(item)
                        continue
                    waiting.discard(device_id)
                    item['proxy']=(reservation['host'],reservation['puerto'])
                    item['laboratory']=bool(reservation.get('lab_shared_exit',False))
                    item['expected_exit_ip']=reservation.get('exit_ip')
                    db.auditar_proxy(owner,device_id,reservation['endpoint'],'reserva','confirmado',
                                     ip_esperada=reservation.get('exit_ip'))
                    Path(item['directory']).mkdir(parents=True,exist_ok=True)
                    item['worker_token']=uuid.uuid4().hex
                    item['started_at']=time.time()
                    lease=Path(item['directory'])/'supervisor_lease.json'
                    lease_data={'device_id':device_id,'serial':route.serial,'host':route.server.host,
                                'port':route.server.port,'hardware_serial':route.hardware_serial,
                                'owner':owner,'worker_token':item['worker_token'],'supervisor_pid':os.getpid(),'pid':None}
                    escribir_json(lease,lease_data)
                    process=ctx.Process(target=farm_worker,name=f"panda-{item['alias']}",
                        args=(item,args,stop,gate,lock,next_request,str(db.path)))
                    try:
                        process.start()
                    except BaseException as exc:
                        allocator.finalizar(device_id,owner,cleanup_ok=True)
                        if auto_heal and isinstance(exc,Exception):
                            lease.unlink(missing_ok=True)
                            failures.append(device_id)
                            db.actualizar_dispositivo(device_id,estado='Error')
                            db.log_granja(owner,device_id,'No se pudo crear el worker',nivel='ERROR',detalle={'error':str(exc)})
                            continue
                        raise
                    started.append((process,item))
                    lease_data['pid']=process.pid
                    escribir_json(lease,lease_data)
                    active[device_id]=(process,item)
                    db.log_granja(owner,device_id,'Proceso iniciado',detalle={'pid':process.pid,'server':route.server.key})
                if slots:
                    next_start=now+(startup_delay() if parallel==1 else 0)
                    escribir_json(run_dir/'manifest.json',{'workers':[{
                        'serial':i['route'].serial,'device_id':clave_placa(i),'host':i['route'].server.host,'port':i['route'].server.port,
                        'alias':i['alias'],'legacy_device_id':i['legacy_device_id'],
                        'hardware_serial':i['route'].hardware_serial,'worker_token':i.get('worker_token'),
                        'pid':p.pid,'directory':i['directory']} for p,i in started]})
                actualizar_recursos()
            stop.wait(.2)
    finally:
        cancelled=stop.is_set()
        stop.set()
        deadline=time.monotonic()+args.shutdown_grace
        latest={clave_placa(item):(process,item) for process,item in started}
        for process,item in started:
            process.join(max(0,deadline-time.monotonic()))
            if process.is_alive():
                process.terminate()
                process.join(10)
                failures.append(clave_placa(item))
            elif process.exitcode and latest[clave_placa(item)][0] is process and not item.get('healed'):
                failures.append(clave_placa(item))
        heal_pool.shutdown(wait=True)
        # Recuperar solo nuestros leases, en el servidor fijado; nunca kill-server.
        def recover(entry):
            process,item=entry
            if process.is_alive():
                allocator.finalizar(clave_placa(item),owner,cleanup_ok=False)
                db.actualizar_dispositivo(clave_placa(item),estado='Cuarentena')
                return clave_placa(item)
            error=cleanup_worker(item,args.package)
            if error is None:
                db.excluir_ip_sin_cuenta(owner,clave_placa(item))
            allocator.finalizar(clave_placa(item),owner,cleanup_ok=error is None)
            if error:
                db.actualizar_dispositivo(clave_placa(item),estado='Cuarentena' if auto_heal else 'Error')
                return clave_placa(item)
            liberar_api(db,item.get('worker_token',''))
            (Path(item['directory'])/'supervisor_lease.json').unlink(missing_ok=True)
            db.actualizar_dispositivo(clave_placa(item),estado='Error' if item.get('terminal_failure') or
                                      (process.exitcode and not item.get('healed')) else 'Espera')
            return None
        with ThreadPoolExecutor(max_workers=min(8,max(1,len(started)))) as executor:
            failures.extend(x for x in executor.map(recover,latest.values()) if x)
        started_ids={clave_placa(item) for _,item in started}
        pending_accounts=[row['id_adb'] for row in db.dispositivos()
                          if row['id_adb'] in started_ids and row.get('cuenta_estado')=='pendiente']
        escribir_json(run_dir/'shutdown.json',{'failures':sorted(set(failures)),
            'started':len(started),'queued_not_started':len(pending),'pending_accounts':pending_accounts})
        for item in pending:
            db.actualizar_dispositivo(clave_placa(item),estado='Espera')
        db.alerta('network_resources','Falta de recursos de red',activa=False)
        db.finalizar_ejecucion(owner,'error' if failures else ('cancelado' if cancelled or pending else
                               ('revision_cuentas' if pending_accounts else 'completado')))
        if smoke:
            db.guardar_resumen_carga(owner,selected)
        for sig,handler in previous.items():
            signal.signal(sig,handler)
    return int(bool(failures))
