"""Orquestación Android: hasta 40 procesos aislados (Python 3.11+)."""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import socket
import sys
import subprocess
import time
from contextlib import suppress
from datetime import datetime, timezone

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.appium_service import AppiumService
from appium.webdriver.client_config import AppiumClientConfig
from config.proxies import ADBError, adb, verificar_adb, configurar_proxy_dispositivo, limpiar_proxy_dispositivo, validar_proxy
from core.actions import ejecutar_swipe_vertical, interactuar_elemento_nativo
from core.ai_agent import analizar_pantalla_y_decidir, extraer_contexto
from core.database import Database
from config.proxies import usar_servidor_adb
from core.adb_pool import descubrir_pool,cargar_servidores
from config.android_app import TIKTOK_PACKAGE, TIKTOK_ACTIVITY, normalizar_activity


class ResultadoInteraccionIncierto(RuntimeError):
    """Una operación externa pudo completarse; no repetirla automáticamente."""


def descubrir_dispositivos():
    snapshot=descubrir_pool()
    return sorted(serial for serial,route in snapshot.devices.items() if route.status=='device')


def construir_plan(devices, proxies, count):
    if not 1 <= count <= 40 or len(devices) < count:
        raise ValueError('Requiere entre 1 y 40 placas autorizadas y conectadas')
    if len(proxies) < count or len(set(proxies)) != len(proxies):
        raise ValueError('Requiere un proxy único por placa, sin duplicados')
    plan = []
    for i, udid in enumerate(devices[:count]):
        host, port = proxies[i].rsplit(':', 1)
        validar_proxy(host, port)
        plan.append(dict(index=i, udid=udid, appium_port=4723+i,
                         system_port=8200+i, mjpeg_port=9200+i,
                         proxy_host=host, proxy_port=int(port)))
    return plan


def comprobar_puertos(plan):
    sockets = []
    try:
        for item in plan:
            for name in ('appium_port','system_port','mjpeg_port'):
                sock = socket.socket()
                sockets.append(sock)
                sock.bind(('127.0.0.1',item[name]))
    finally:
        for sock in sockets:
            sock.close()


def auditar(path, event, **data):
    with path.open('a',encoding='utf-8') as file:
        file.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
                                   event=event, **data),ensure_ascii=False)+'\n')


def configurar_driver(item, args):
    options = UiAutomator2Options().load_capabilities({
        'platformName':'Android', 'appium:automationName':'UiAutomator2',
        'appium:udid':item['udid'], 'appium:deviceName':item['udid'],
        'appium:remoteAdbHost':item.get('adb_host','127.0.0.1'),
        'appium:adbPort':item.get('adb_port',5037),
        'appium:systemPort':item['system_port'],
        'appium:mjpegServerPort':item['mjpeg_port'],
        'appium:noReset':True, 'appium:appPackage':args.package,
        'appium:appActivity':args.activity, 'appium:appWaitActivity':'*',
        'appium:newCommandTimeout':120, 'appium:adbExecTimeout':20000,
        'appium:uiautomator2ServerReadTimeout':30000})
    url = f"http://127.0.0.1:{item['appium_port']}"
    return webdriver.Remote(url, options=options,
        client_config=AppiumClientConfig(remote_server_addr=url,timeout=45))


def aplicar_decision(driver, decision, selectors, audit, on_action=lambda event:None):
    # Selectores estáticos de la versión instalada, nunca generados por la IA.
    if decision['dar_like']:
        interactuar_elemento_nativo(driver, selectors['like'])
        auditar(audit,'like_click')
        on_action('like_click')
    if decision['comentar']:
        interactuar_elemento_nativo(driver, selectors['comments'])
        field = interactuar_elemento_nativo(driver, selectors['comment_input'])
        field.clear()
        field.send_keys(decision['texto_comentario'])
        interactuar_elemento_nativo(driver, selectors['comment_send'])
        auditar(audit,'comment_send_click')
        on_action('comment_send_click')
        interactuar_elemento_nativo(driver, selectors['comment_close'])


def worker(item, args, selectors, stop, api_gate, rate_lock, next_request, run_dir):
    with usar_servidor_adb(item.get('adb_host','127.0.0.1'),item.get('adb_port',5037)):
        return _worker(item,args,selectors,stop,api_gate,rate_lock,next_request,run_dir)


def _worker(item, args, selectors, stop, api_gate, rate_lock, next_request, run_dir):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    audit = Path(run_dir)/f"device-{item['index']:02d}.jsonl"
    service, driver, proxy_attempted = AppiumService(), None, False
    failed, cycle = 0, 0
    database,interaction_id,attempt = None,None,0
    final_state='Espera'
    try:
        if stop.wait(item['index']*args.stagger):
            return
        database=Database()
        database.actualizar_dispositivo(item['udid'],
            proxy=f"{item['proxy_host']}:{item['proxy_port']}",estado='Espera',conectado=True)
        auditar(audit,'start',udid=item['udid'],appium_port=item['appium_port'],
                system_port=item['system_port'])
        service.start(args=['--address','127.0.0.1','--port',str(item['appium_port']),
                            '--log',str(Path(run_dir)/f"appium-{item['index']:02d}.log")],
                      timeout_ms=60000)
        if not service.is_listening:
            raise RuntimeError('Appium no está escuchando')
        while not stop.is_set() and (args.cycles == 0 or cycle < args.cycles):
            attempt+=1
            side_effect_possible = False
            try:
                if adb('-s',item['udid'],'get-state') != 'device':
                    raise RuntimeError('Dispositivo desconectado')
                database.actualizar_dispositivo(item['udid'],estado='Calentando',conectado=True)
                if driver is None:
                    proxy_attempted = True
                    configurar_proxy_dispositivo(item['udid'],item['proxy_host'],item['proxy_port'])
                    auditar(audit,'proxy_verified')
                    driver = configurar_driver(item,args)
                if driver.current_package != args.package:
                    driver.activate_app(args.package)
                    stop.wait(2)
                    continue
                context = extraer_contexto(driver.page_source)
                while not stop.is_set():
                    if api_gate.acquire(timeout=1):
                        break
                else:
                    break
                try:
                    with rate_lock:
                        now = time.monotonic()
                        slot = max(now,next_request.value)
                        next_request.value = slot+60/args.rpm
                    if stop.wait(max(0,slot-time.monotonic())):
                        break
                    ai_started=time.perf_counter()
                    decision = analizar_pantalla_y_decidir(driver,contexto=context)
                    latency_ms=(time.perf_counter()-ai_started)*1000
                finally:
                    api_gate.release()
                digest = hashlib.sha256(context.encode()).hexdigest()
                auditar(audit,'decision',cycle=cycle,context_sha256=digest,decision=decision)
                interaction_id=database.registrar_interaccion(item['udid'],run_id=Path(run_dir).name,
                    ciclo=attempt,descripcion_video=context,latencia_ms=latency_ms,
                    decision_ia={**decision,'interactuar':decision['dar_like'] or decision['comentar']})
                if args.execute:
                    if extraer_contexto(driver.page_source) != context:
                        auditar(audit,'stale_screen_skipped')
                    else:
                        try:
                            side_effect_possible = decision['dar_like'] or decision['comentar']
                            aplicar_decision(driver,decision,selectors,audit,
                                on_action=lambda event: database.registrar_accion(
                                    interaction_id,event,decision['texto_comentario']))
                        except Exception as exc:
                            raise ResultadoInteraccionIncierto() from exc
                telemetry = ejecutar_swipe_vertical(driver)
                auditar(audit,'swipe',cycle=cycle,telemetry=telemetry)
                database.finalizar_interaccion(interaction_id)
                interaction_id=None
                cycle += 1
                failed = 0
                stop.wait(args.interval)
            except Exception as exc:
                if interaction_id is not None:
                    database.finalizar_interaccion(interaction_id,error=type(exc).__name__)
                    interaction_id=None
                database.actualizar_dispositivo(item['udid'],estado='Error')
                if side_effect_possible or isinstance(exc, ResultadoInteraccionIncierto):
                    raise
                failed += 1
                # No se reintenta el mismo clic/comentario: resultado puede ser ambiguo.
                auditar(audit,'cycle_error',cycle=cycle,error_type=type(exc).__name__,
                        consecutive_failures=failed)
                if driver:
                    with suppress(Exception):
                        driver.quit()
                    driver = None
                if failed >= args.max_failures:
                    raise RuntimeError('Límite de fallos consecutivos alcanzado') from exc
                if stop.wait(min(30,2**failed)):
                    break
    except Exception as exc:
        final_state='Error'
        auditar(audit,'fatal',error_type=type(exc).__name__)
        raise
    finally:
        if database:
            with suppress(Exception):
                database.actualizar_dispositivo(item['udid'],estado=final_state)
        if driver:
            with suppress(Exception):
                driver.quit()
        if proxy_attempted:
            try:
                limpiar_proxy_dispositivo(item['udid'])
                auditar(audit,'proxy_cleared')
            except Exception as exc:
                auditar(audit,'cleanup_required',udid=item['udid'],error_type=type(exc).__name__)
                if database:
                    with suppress(Exception):
                        database.actualizar_dispositivo(item['udid'],estado='Error')
        with suppress(Exception):
            service.stop()


def procesar_ciclo_navegacion_asistida(page, account_id: str, *, selectors=None,
                                      client=None, execute=False, record=lambda *a, **k: None,warmup=False,stop=None,telemetry=None):
    """Un ciclo síncrono por proceso; nunca comparte Page entre cuentas.

    El supervisor gestiona la concurrencia y aporta el cliente con límite global.
    La API síncrona coincide con el contrato del navegador existente.
    """
    from core.web_orchestrator import ejecutar_ciclo_web
    if selectors is None:
        selectors = json.loads(Path('config/web_selectors.json').read_text(encoding='utf-8-sig'))
    return ejecutar_ciclo_web(page, account_id, selectors, client, execute=execute, record=record,warmup=warmup,stop=stop,telemetry=telemetry)


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui',action='store_true',help='Abrir dashboard Streamlit local, sin requerir ADB')
    parser.add_argument('--host-tunnel-check',action='store_true',help='Diagnóstico acotado del motor Windows; no despliega APK Android')
    parser.add_argument('--tunnel-device',default='tun0')
    parser.add_argument('--tunnel-proxy',default='http://192.168.1.199:8001')
    parser.add_argument('--tunnel-rest-api',default='127.0.0.1:6060')
    parser.add_argument('--web-accounts',type=Path,help='JSON de cuentas web; modo independiente de ADB')
    parser.add_argument('--web-selectors',type=Path,default=Path('config/web_selectors.json'))
    parser.add_argument('--web-login-only',action='store_true',help='Abrir perfiles web para autenticación manual, sin IA')
    parser.add_argument('--web-headless',action='store_true',help='Ejecutar perfiles web sin ventana')
    parser.add_argument('--web-engine',choices=['playwright','patchright'],default='playwright')
    parser.add_argument('--web-async',action='store_true',help='DOM y OpenAI async en workers web con ciclos finitos')
    parser.add_argument('--poc-ui',action='store_true',help='Abrir panel nativo Tk de POC QA (sin iniciar pruebas automáticamente)')
    parser.add_argument('--web-load-base',type=float,default=6,help='Base QA determinista de retención async (0–30 s)')
    parser.add_argument('--web-telemetry-db',type=Path,default=Path(__file__).resolve().parent/'sessions/telemetry_qa.db')
    parser.add_argument('--web-warmup',action='store_true',help='Observar DOM durante 10–25 segundos antes de cada decisión')
    parser.add_argument('--simulate-env',action='store_true',help='Simulación explícita sin ADB/OpenAI; base aislada data/simulation.db')
    parser.add_argument('--start-farm',action='store_true',help='Orquestación ADB con firewall y pool de servidores')
    parser.add_argument('--network-mode',choices=['root','proxy-laboratory','vpn-lockdown'],default='root',
        help='root: firewall estricto; proxy-laboratory: proxy y datos móviles sin garantizar aislamiento WiFi')
    parser.add_argument('--stop-file',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--bootstrap-parallelism',type=int,default=40,help='Conexiones y arranques paralelos (1–40)')
    parser.add_argument('--bootstrap-timeout',type=float,default=30,help='Ventana de espera al encendido del hardware (1–300 s)')
    parser.add_argument('--worker-timeout',type=float,default=180,help='Watchdog: segundos sin heartbeat antes de recuperar una placa')
    parser.add_argument('--auto-heal-attempts',type=int,default=2,help='Reintentos aislados por placa tras fallo recuperable (0–5)')
    parser.set_defaults(auto_heal=True)
    parser.add_argument('--smoke-test',type=int,metavar='N',help='Smoke test sobre un subset inicial fijo de N placas (1–40)')
    parser.add_argument('--adb-servers',type=Path,help='JSON de servidores ADB; defecto config/adb_servers.json')
    parser.add_argument('--shutdown-grace',type=float,default=180,help='Segundos de cierre cooperativo antes de recuperar leases')
    parser.add_argument('--diagnostic-session',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--devices',type=int,default=40,help='1–40, valor por defecto 40')
    parser.add_argument('--proxies',type=Path,default=Path('config/proxies.txt'))
    parser.add_argument('--proxy-pool',type=Path,default=Path('config/proxy_pool.json'),help='Pool JSON reservado transaccionalmente por --start-farm')
    parser.add_argument('--feed-markers',type=Path,help='JSON con lista markers de IDs/accessibility del reproductor/feed')
    parser.add_argument('--selectors',type=Path,default=Path('config/selectors.json'))
    parser.add_argument('--package',default=TIKTOK_PACKAGE)
    parser.add_argument('--activity',help='Activity real de la versión instalada')
    parser.add_argument('--test-device',action='store_true',help='Prueba en el primer USB; control ADB sin Appium')
    parser.add_argument('--diagnose-device',action='store_true',help='Diagnóstico físico interactivo sin OpenAI ni proxy obligatorio')
    parser.add_argument('--proxy',help='Proxy de la prueba individual: hostname:puerto')
    parser.add_argument('--expected-exit-ip',help='IP pública de salida esperada según el proveedor; no IP de entrada del proxy')
    parser.add_argument('--open-tiktok',action='store_true',help='Abrir TikTok bajo firewall y ejecutar el ciclo IA/ADB')
    parser.add_argument('--ai-videos',type=int,default=5,help='Videos para el ciclo IA/ADB individual (1–20)')
    parser.add_argument('--map-only',action='store_true',help='Mantener el mapeo de Etapa 2 sin consultar IA')
    parser.add_argument('--cycles',type=int,default=10,help='0 = continuo')
    parser.add_argument('--execute',action='store_true',help='Aplicar likes/comentarios; por defecto solo auditoría y swipe')
    parser.add_argument('--plan',action='store_true',help='Descubrir y validar sin modificar dispositivos')
    parser.add_argument('--rpm',type=float,default=30,help='Máximo global de inicios de consulta/minuto')
    parser.add_argument('--api-concurrency',type=int,default=4)
    parser.add_argument('--stagger',type=float,default=2)
    parser.add_argument('--interval',type=float,default=3)
    parser.add_argument('--max-failures',type=int,default=5)
    args = parser.parse_args()
    if not 0 <= args.web_load_base <= 30:
        parser.error('--web-load-base requiere un valor finito entre 0 y 30')
    if args.poc_ui:
        if any((args.ui,args.web_accounts,args.web_async,args.start_farm,args.simulate_env,args.test_device,
                args.diagnose_device,args.open_tiktok,args.execute,args.plan,args.smoke_test is not None)):
            parser.error('--poc-ui es una interfaz independiente')
        return args
    if args.host_tunnel_check and any((args.ui,args.web_accounts,args.simulate_env,args.start_farm,
                                     args.smoke_test is not None,args.test_device,args.diagnose_device)):
        parser.error('--host-tunnel-check es un modo independiente')
    if not 1<=args.bootstrap_parallelism<=40 or not 1<=args.bootstrap_timeout<=300 or not 30<=args.worker_timeout<=3600 or not 0<=args.auto_heal_attempts<=5:
        parser.error('Bootstrap: paralelismo 1–40, espera 1–300 s, watchdog 30–3600 s y auto-heal 0–5')
    if args.activity is None and args.package==TIKTOK_PACKAGE and (
            args.smoke_test is not None or args.start_farm or args.open_tiktok
            or not (args.ui or args.test_device or args.diagnose_device)):
        args.activity=TIKTOK_ACTIVITY
    if args.activity and args.activity!='ACTIVITY_REAL':
        try:
            args.activity=normalizar_activity(args.package,args.activity)
        except ValueError as exc:
            parser.error(str(exc))
    if args.smoke_test is not None:
        if not 1<=args.smoke_test<=40:
            parser.error('--smoke-test requiere un número entre 1 y 40')
        args.start_farm=True
        args.devices=min(args.devices,args.smoke_test)
        if args.cycles==0:
            parser.error('--smoke-test requiere --cycles finito para limitar la prueba')
    if (args.web_login_only or args.web_headless) and not args.web_accounts:
        parser.error('--web-login-only y --web-headless requieren --web-accounts')
    if args.web_async and (not args.web_accounts or (args.cycles <= 0 and not args.web_login_only)):
        parser.error('--web-async requiere --web-accounts y --cycles mayor que cero salvo login manual')
    if args.web_login_only and (args.web_headless or args.execute):
        parser.error('La autenticación manual requiere ventana visible y no admite --execute')
    if args.web_accounts and any((args.ui,args.simulate_env,args.start_farm,args.test_device,args.diagnose_device,args.open_tiktok,args.map_only)):
        parser.error('--web-accounts se ejecuta como modo independiente de Android')
    if args.stop_file and not (args.start_farm or args.web_accounts):
        parser.error('--stop-file requiere --start-farm o --smoke-test')
    if args.ui:
        if args.test_device or args.diagnose_device or args.start_farm:
            parser.error('--ui se ejecuta como modo independiente')
    elif args.start_farm:
        if args.test_device or args.diagnose_device or args.open_tiktok or args.map_only:
            parser.error('--start-farm no combina con los modos individuales')
        if not args.activity or args.activity=='ACTIVITY_REAL':
            parser.error('--start-farm requiere la activity real instalada')
    elif args.diagnose_device:
        if not args.test_device:
            parser.error('--diagnose-device requiere --test-device')
        if args.proxy or args.expected_exit_ip or args.open_tiktok or args.execute or args.plan:
            parser.error('El diagnóstico usa el estado de red existente; no combinar con proxy, arranque, execute o plan')
    elif args.test_device:
        if not args.proxy or not args.expected_exit_ip:
            parser.error('--test-device requiere --proxy y --expected-exit-ip')
        if args.open_tiktok and not args.activity:
            args.activity = TIKTOK_ACTIVITY if args.package==TIKTOK_PACKAGE else None
        if args.open_tiktok and args.activity == 'ACTIVITY_REAL':
            parser.error('Reemplaza ACTIVITY_REAL por la activity instalada')
    elif not args.activity:
        parser.error('--activity es obligatorio para el clúster')
    elif args.open_tiktok or args.proxy or args.expected_exit_ip or args.map_only:
        parser.error('--open-tiktok, --proxy, --expected-exit-ip y --map-only requieren --test-device')
    if not 1<=args.ai_videos<=20:
        parser.error('--ai-videos requiere 1–20')
    if args.diagnostic_session and not args.diagnose_device:
        parser.error('--diagnostic-session requiere --diagnose-device')
    if not 1<=args.devices<=40 or args.cycles<0 or args.rpm<=0 or args.api_concurrency<1 or args.max_failures<1 or min(args.interval,args.stagger)<0 or args.shutdown_grace<1:
        parser.error('Parámetros numéricos fuera de rango')
    if args.network_mode!='root' and not args.start_farm:
        parser.error('--network-mode proxy-laboratory requiere --start-farm o --smoke-test')
    return args


def main():
    args = argumentos()
    if args.poc_ui:
        from ui.poc_dashboard import main as abrir_poc
        abrir_poc()
        return 0
    from core.project_env import load_project_environment
    load_project_environment()
    if args.host_tunnel_check:
        from core.network_tunnel import iniciar_motor_tunel_tcp,TunnelError
        try:
            motor=iniciar_motor_tunel_tcp(device=args.tunnel_device,proxy=args.tunnel_proxy,restAPI=args.tunnel_rest_api)
            try:
                motor.finalizado.wait(20)
                print('Motor del host: '+motor.estado+'; despliegue Android no acreditado.')
                return 0 if motor.estado=='activo' else 2
            finally:
                if motor.process.poll() is None:
                    motor.cerrar()
        except TunnelError:
            return 2
    if args.web_accounts:
        from core.web_orchestrator import iniciar_cuentas_web
        try:
            return iniciar_cuentas_web(args)
        except (ValueError,OSError,RuntimeError) as exc:
            print(f'Arranque web bloqueado ({type(exc).__name__}). Revisa configuración y reservas.',file=sys.stderr)
            return 2
    if args.simulate_env:
        if args.ui:
            os.environ['TIKTOK_DB_PATH']=str(Path(__file__).resolve().parent/'data/simulation.db')
            os.environ['PANDA_SIMULATION']='1'
        else:
            from core.deployment_check import simular_entorno
            return simular_entorno(args)
    if args.adb_servers:
        os.environ['ADB_SERVERS_CONFIG']=str(args.adb_servers.resolve())
        Database().guardar_servidores(cargar_servidores(args.adb_servers))
    if args.ui:
        root=Path(__file__).resolve().parent
        return subprocess.call([sys.executable,'-m','streamlit','run',str(root/'ui/dashboard.py'),
                                '--server.address','127.0.0.1','--server.port','8501',
                                '--server.headless','true',
                                '--browser.gatherUsageStats','false'],cwd=root)
    if args.start_farm:
        from core.deployment_check import fijar_adb_local
        try:
            fijar_adb_local()
        except (ValueError, OSError, ADBError) as exc:
            print(f'Preflight bloqueado: {exc}',file=sys.stderr)
            return 2
    verificar_adb()
    if args.start_farm:
        from core.mass_orchestrator import iniciar_granja
        try:
            return iniciar_granja(args)
        except (ValueError,OSError,ADBError) as exc:
            print(f'Arranque bloqueado: {exc}',file=sys.stderr)
            return 2
    if args.diagnose_device:
        from core.diagnostics import diagnosticar_dispositivo
        if args.diagnostic_session:
            from core.diagnostic_bridge import DiagnosticBridge
            bridge=DiagnosticBridge(args.diagnostic_session)
            result=diagnosticar_dispositivo(package=args.package,directory=bridge.directory,
                preguntar=bridge.preguntar,check=bridge.comprobar_cancelacion,open_viewer=False)
        else:
            result = diagnosticar_dispositivo(package=args.package)
        return 0 if result['status']=='passed' else 2
    if args.test_device:
        from config.device_test import ejecutar_prueba_dispositivo
        launch = args.open_tiktok or bool(args.activity and args.activity!='ACTIVITY_REAL' and not args.map_only)
        ai_videos = args.ai_videos if launch and not args.map_only else 0
        if ai_videos and not os.getenv('OPENAI_API_KEY'):
            raise ValueError('Define OPENAI_API_KEY para la Etapa 3 o usa --map-only')
        ejecutar_prueba_dispositivo(args.proxy, args.expected_exit_ip,
            package=args.package, activity=args.activity if launch else None,
            map_ui=bool(args.activity), ai_videos=ai_videos)
        return 0
    proxies = [line.strip() for line in args.proxies.read_text().splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    snapshot=descubrir_pool(cargar_servidores(args.adb_servers))
    Database().sincronizar_pool(snapshot)
    plan = construir_plan(sorted(s for s,r in snapshot.devices.items() if r.status=='device'),proxies,args.devices)
    for item in plan:
        route=snapshot.devices[item['udid']]
        item.update(adb_host=route.server.host,adb_port=route.server.port)
    comprobar_puertos(plan)
    if args.plan:
        print(json.dumps([{k:v for k,v in x.items() if not k.startswith('proxy')}
                          for x in plan],indent=2))
        return 0
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError('Define OPENAI_API_KEY')
    selectors = json.loads(args.selectors.read_text(encoding='utf-8')) if args.execute else {}
    if args.execute and any(not selectors.get(k) or selectors[k].startswith('REEMPLAZAR')
        for k in ('like','comments','comment_input','comment_send','comment_close')):
        raise ValueError('Configura todos los selectores nativos antes de --execute')
    run_dir = Path('runs')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir.mkdir(parents=True)
    ctx = mp.get_context('spawn')
    stop, gate, lock = ctx.Event(), ctx.BoundedSemaphore(args.api_concurrency), ctx.Lock()
    next_request = ctx.Value('d',0)
    processes = []
    try:
        for item in plan:
            process = ctx.Process(target=worker,name=f"android-{item['index']}",
                args=(item,args,selectors,stop,gate,lock,next_request,str(run_dir)))
            process.start()
            processes.append(process)
        while any(p.is_alive() for p in processes):
            if any(p.exitcode not in (None,0) for p in processes):
                stop.set()
            time.sleep(.5)
    except KeyboardInterrupt:
        stop.set()
    finally:
        stop.set()
        deadline = time.monotonic()+120
        for process in processes:
            process.join(max(0,deadline-time.monotonic()))
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(10)
                auditar(run_dir/'supervisor.jsonl','forced_termination',process=process.name)
        # Segundo intento también cubre cierre forzado del worker y desconexiones breves.
        for item in plan:
            try:
                with usar_servidor_adb(item['adb_host'],item['adb_port']):
                    limpiar_proxy_dispositivo(item['udid'])
            except Exception as exc:
                auditar(run_dir/'supervisor.jsonl','cleanup_required',udid=item['udid'],
                        error_type=type(exc).__name__)
    return int(any(p.exitcode != 0 for p in processes))


if __name__ == '__main__':
    mp.freeze_support()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Prueba interrumpida; finalizó la limpieza del contexto.')
        raise SystemExit(130)
    except (ADBError, ValueError, OSError) as exc:
        print(f'Error de inicialización: {exc}', file=sys.stderr)
        raise SystemExit(1)
