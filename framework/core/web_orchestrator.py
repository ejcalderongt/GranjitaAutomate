"""Cuentas web en procesos aislados, con reservas de red y auditoría local."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import time
import random
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

from core.browser import ROOT, validar_account_id, directorio_cuenta, iniciar_navegador_tiktok, cerrar_contexto_seguro
from core.actions import guardar_evidencia_visual, hacer_swipe_down_movil, escribir_comentario_movil
from core.actions import simular_movimiento_tactil_humano, hacer_swipe_feed_tiktok
from config.proxies import leer_proxy_pool, ProxyAllocator
from core.database import Database
from core.runtime_health import ParadaRecuperable, ClienteRecuperable, liberar_api


def construir_plan_web(accounts, entries):
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 40:
        raise ValueError('La lista web requiere entre 1 y 40 cuentas')
    enabled = [item for item in entries if item.get('enabled', True)]
    plan, names, endpoints, profiles = [], set(), set(), set()
    for index, account in enumerate(accounts):
        if isinstance(account, str):
            account = {'id': account}
        if not isinstance(account, dict):
            raise ValueError('Cada cuenta requiere un identificador')
        name = validar_account_id(account.get('id'))
        profile=validar_account_id(account.get('profile',name))
        if profile.casefold() in profiles:
            raise ValueError('Cada proceso requiere un perfil persistente exclusivo')
        profiles.add(profile.casefold())
        proxy = next((p for p in enabled if p['endpoint'] == account['proxy']), None) if account.get('proxy') else (
            enabled[index] if index < len(enabled) else None)
        if name.casefold() in names or proxy is None or proxy['endpoint'] in endpoints:
            raise ValueError('Cuentas únicas y un proxy habilitado exclusivo por cuenta son obligatorios')
        names.add(name.casefold())
        endpoints.add(proxy['endpoint'])
        plan.append({'id': name, 'profile':profile, 'proxy': proxy})
    if any(not p['proxy'].get('exit_ip') for p in plan):
        raise ValueError('Configura la IP de salida esperada de cada proxy')
    exits = [p['proxy']['exit_ip'] for p in plan if not p['proxy'].get('lab_shared_exit')]
    if len(exits) != len(set(exits)):
        raise ValueError('Producción requiere IPs de salida diferentes')
    return plan


def elemento_unico(page, selector):
    matches = page.locator(selector)
    visible = [matches.nth(i) for i in range(matches.count()) if matches.nth(i).is_visible()]
    if len(visible) != 1:
        raise ValueError('El selector debe identificar exactamente un elemento visible')
    return visible[0]


def ejecutar_ciclo_web(page, account, selectors, client, *, execute=False, record=lambda *a, **k: None,
                       warmup=False, stop=None, telemetry=None):
    from core.ai_agent import evaluar_con_openai
    from core.scraper import extraer_contexto_video
    from core.decision_telemetry import DecisionTelemetry
    telemetry = telemetry if telemetry is not None else DecisionTelemetry(account)
    cycle_id = uuid4().hex
    external_record = record
    def record(event, **data):
        telemetry.append(event, cycle_id=cycle_id, **data)
        external_record(event, **data)
    # El operador valida los selectores de sesión y del video activo para su versión web.
    if page.locator(selectors['login']).is_visible():
        record('Pendiente Cuenta')
        raise ValueError('La sesión requiere autenticación manual')
    elemento_unico(page, selectors['authenticated'])
    active = elemento_unico(page, selectors['active_video'])
    if warmup:
        duration=random.uniform(10,25)
        until=time.monotonic()+duration
        record('Observación DOM',duration_seconds=round(duration,2))
        while time.monotonic()<until:
            if stop is not None and stop.is_set():
                raise InterruptedError('Cierre solicitado')
            active.inner_text(timeout=5000)
            page.wait_for_timeout(min(500,max(0,(until-time.monotonic())*1000)))
    description=active.locator("div[data-e2e='video-desc']").first if warmup else active
    content = description.inner_text(timeout=5000)[:4000]
    identity = active.get_attribute('data-e2e') or ''
    if not content.strip():
        raise ValueError('El video no tiene contexto textual suficiente')
    record('Analizando con IA')
    metadata = extraer_contexto_video(page, scope=active, selectors=selectors.get('metadata'),
        aviso=lambda **data: record('metadata_warning', **data))
    record('context', contexto=metadata, source='active_video_dom')
    started = time.perf_counter()
    try:
        rich_decision = evaluar_con_openai(client, metadata)
    except Exception as exc:
        record('ai_error', error_type=type(exc).__name__, latency_ms=round((time.perf_counter()-started)*1000, 2))
        raise
    latency_ms = round((time.perf_counter()-started)*1000, 2)
    decision = {'dar_like': rich_decision['dar_like'], 'comentar': rich_decision['comentar'],
                'texto_comentario': rich_decision['comentario']}
    evidence = guardar_evidencia_visual(page, account, 'post_decision')
    record('decision', decision=rich_decision, contexto=metadata, evidencia=bool(evidence),
        latency_ms=latency_ms, model='gpt-4o-mini', prompt_version='video_metadata_v1',
        execute_enabled=execute, context_sufficient=metadata['descripcion'] not in ('', 'Sin descripción'))
    if rich_decision['compartir']:
        record('share_not_executed', reason='unsupported_action')

    def aviso(stage, exc):
        print(f'{account}: aviso en {stage} ({type(exc).__name__}); acción sin reintento', flush=True)
        record('Aviso', stage=stage, error_type=type(exc).__name__)

    allow_actions = execute and evidence is not None
    if execute and evidence is None:
        aviso('evidencia', RuntimeError())
    if allow_actions:
        try:
            current = elemento_unico(page, selectors['active_video'])
            current_description=current.locator("div[data-e2e='video-desc']").first if warmup else current
            if current_description.inner_text(timeout=5000)[:4000] != content or (current.get_attribute('data-e2e') or '') != identity:
                raise RuntimeError('El contenido cambió durante el análisis')
            if extraer_contexto_video(page, scope=current, selectors=selectors.get('metadata')) != metadata:
                raise RuntimeError('Los metadatos cambiaron durante el análisis')
        except Exception as exc:
            allow_actions = False
            aviso('contenido', exc)
    if allow_actions and decision['dar_like']:
        try:
            # El contenedor activo evita seleccionar controles de otro video precargado.
            like = (elemento_unico(page, selectors['like']) if selectors.get('like')
                    else active.locator("span[data-e2e='like-icon']").first)
            control = like
            state = control.get_attribute('aria-pressed', timeout=5000)
            if state not in ('true', 'false'):
                control = like.locator('xpath=ancestor::*[@aria-pressed][1]')
                state = control.get_attribute('aria-pressed', timeout=5000)
            if state not in ('true', 'false'):
                raise ValueError('Estado de like no verificable')
            if state == 'false':
                if warmup:
                    simular_movimiento_tactil_humano(page,
                        selector_destino=selectors.get('like') or "span[data-e2e='like-icon']",
                        scope=None if selectors.get('like') else active)
                else:
                    control.click(timeout=5000)
                guardar_evidencia_visual(page, account, 'post_like')
                record('like_click')
        except Exception as exc:
            aviso('like', exc)
    comment_panel_safe = True
    if allow_actions and decision['comentar']:
        try:
            comments = (elemento_unico(page, selectors['comments']) if selectors.get('comments')
                        else active.locator("span[data-e2e='comment-icon']").first)
            comment_panel_safe = False
            comments.click(timeout=5000)
            field = (elemento_unico(page, selectors['comment_input']) if selectors.get('comment_input')
                     else page.locator("div[data-e2e='comment-input'] input, .comment-input-area-v2").first)
            escribir_comentario_movil(page, field, decision['texto_comentario'])
            if warmup:
                page.keyboard.press('Enter')
            else:
                elemento_unico(page, selectors['comment_send']).click(timeout=5000)
            guardar_evidencia_visual(page, account, 'post_comentario')
            record('comment_send_click')
        except Exception as exc:
            aviso('comentario', exc)
        finally:
            try:
                elemento_unico(page, selectors['comment_close']).click(timeout=5000)
                comment_panel_safe = True
            except Exception as exc:
                aviso('cerrar_comentarios', exc)
    if not comment_panel_safe:
        # No arrastrar sobre un formulario con texto pendiente de envío.
        record('Recuperación de interfaz requerida')
        raise RuntimeError('No se confirmó el cierre del panel de comentarios')
    try:
        if warmup:
            hacer_swipe_feed_tiktok(page,account)
        else:
            hacer_swipe_down_movil(page, account)
        record('Navegando')
        return True
    except Exception as exc:
        aviso('desplazamiento', exc)
        return False


def worker_web(item, args, selectors, run_id, stop, status):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if getattr(args, 'web_async', False):
        import asyncio
        from core.async_web_orchestrator import worker_web_async
        asyncio.run(worker_web_async(item,args,selectors,run_id,stop,status))
        return
    name, token = item['id'], uuid4().hex
    playwright = context = db = None
    clean, failed = True, False
    folder = directorio_cuenta(ROOT/'logs', name)
    audit = folder/f'{run_id}.jsonl'
    from core.decision_telemetry import DecisionTelemetry
    telemetry = DecisionTelemetry(name, run_id)

    def record(event, **data):
        row = {'time': datetime.now(timezone.utc).isoformat(), 'event': event, **data}
        with audit.open('a', encoding='utf-8') as file:
            file.write(json.dumps(row, ensure_ascii=False)+'\n')
        temporary = Path(str(status)+'.tmp')
        temporary.write_text(json.dumps({'heartbeat':time.time(), 'event':event}), encoding='utf-8')
        temporary.replace(status)

    try:
        record('Inicio')
        db = Database()
        # Una creación interrumpida puede dejar procesos de navegador: retener la reserva.
        clean = False
        browser_proxy=dict(item['proxy'])
        for key in ('username','password'):
            value=os.getenv('PANDA_WEB_PROXY_'+key.upper())
            if value:
                browser_proxy[key]=value
        playwright, context, page = iniciar_navegador_tiktok(item.get('profile',name), browser_proxy,
            headless=args.web_headless,engine=getattr(args,'web_engine','playwright'))
        from core.network_audit import verificar_proxy_auditable
        def observed_exit():
            response = page.request.get('https://api.ipify.org', timeout=15000)
            if not response.ok:
                raise ValueError('No se pudo verificar la salida del proxy')
            return response.text()
        verificar_proxy_auditable(db,ProxyAllocator(db),run_id,'web:'+name,item['proxy']['endpoint'],
            leer_configuracion=lambda:item['proxy']['endpoint'],consultar_salida=observed_exit,
            expected_ip=item['proxy'].get('exit_ip'),
            alcance='Playwright: proxy configurado + HTTPS APIRequestContext; no acredita tráfico del reproductor')
        page.goto('https://www.tiktok.com/foryou', wait_until='domcontentloaded')
        if args.web_login_only:
            record('Autenticación manual: cerrar la ventana al terminar')
            while not stop.wait(.5) and not page.is_closed():
                record('Autenticación manual')
            return
        from core.ai_agent import cliente
        client = ClienteRecuperable(cliente(), db, token, run_id, 'web:'+name, stop,
            args.rpm, args.api_concurrency, heartbeat=lambda: record('Analizando con IA'))
        cycle = 0
        advanced = True
        while not stop.is_set() and (args.cycles == 0 or cycle < args.cycles):
            from main import procesar_ciclo_navegacion_asistida
            advanced = procesar_ciclo_navegacion_asistida(page, name, selectors=selectors, client=client,
                execute=args.execute and advanced, record=record,warmup=getattr(args,'web_warmup',False),stop=stop,
                telemetry=telemetry)
            cycle += 1
            stop.wait(args.interval)
    except Exception as exc:
        failed = True
        if db is not None:
            db.auditar_proxy(run_id,'web:'+name,item['proxy'].get('endpoint'),'ejecucion','fallido',
                error_tipo=type(exc).__name__,alcance='Web: fallo de ejecución; consultar auditoría JSONL')
        record('Error', error_type=type(exc).__name__)
        print(f'{name}: error {type(exc).__name__}; revisar auditoría local', flush=True)
    finally:
        if context is not None or playwright is not None:
            clean = cerrar_contexto_seguro(context, playwright)
        if db is not None:
            with suppress(Exception):
                liberar_api(db, token)
        record('Finalizado', clean=clean, failed=failed)
        Path(str(status)+'.result').write_text(json.dumps({'clean':clean, 'failed':failed}), encoding='utf-8')


def iniciar_cuentas_web(args):
    from core.mass_orchestrator import bloquear_granja
    accounts = json.loads(args.web_accounts.read_text(encoding='utf-8-sig'))
    entries = leer_proxy_pool(args.proxy_pool)
    plan = construir_plan_web(accounts, entries)
    selectors = {} if args.web_login_only else json.loads(args.web_selectors.read_text(encoding='utf-8-sig'))
    required = ['login', 'authenticated', 'active_video']
    if args.execute:
        required += ['comment_close'] if getattr(args,'web_warmup',False) else ['comment_send','comment_close']
    if not args.web_login_only and any(not isinstance(selectors.get(key), str) or
            not selectors[key].strip() or 'REEMPLAZAR' in selectors[key] for key in required):
        raise ValueError('Configura y valida los selectores web antes de iniciar')
    if not args.web_login_only and not os.getenv('OPENAI_API_KEY'):
        raise ValueError('Falta OPENAI_API_KEY')
    if args.plan:
        print(json.dumps([{'id':p['id'],'proxy':p['proxy']['endpoint']} for p in plan], indent=2))
        return 0
    if any(p['proxy'].get('lab_shared_exit') for p in plan):
        print('Laboratorio: endpoints exclusivos con IP pública compartida.', flush=True)
    if getattr(args,'web_async',False):
        from core.telemetry import inicializar_db_telemetria
        args.web_telemetry_db = inicializar_db_telemetria(args.web_telemetry_db)
    run_id = 'web-'+uuid4().hex
    run_folder = ROOT/'runs'/run_id
    run_folder.mkdir(parents=True)
    ctx = mp.get_context('spawn')
    stop, jobs, reserved = ParadaRecuperable(ctx), [], []
    allocator = ProxyAllocator(Database())
    with bloquear_granja(ROOT/'sessions'/'farm.lock'):
        allocator.sincronizar(entries)
        try:
            for item in plan:
                if allocator.reservar('web:'+item['id'], run_id, item['proxy']['endpoint']) is None:
                    raise ValueError('Un proxy o cuenta ya tiene una reserva activa o en cuarentena')
                reserved.append(item)
            for item in plan:
                status = run_folder/(item['id']+'.json')
                status.write_text(json.dumps({'heartbeat':time.time(), 'event':'Preparando proceso'}), encoding='utf-8')
                process = ctx.Process(target=worker_web, name='web-'+item['id'],
                    args=(item, args, selectors, run_id, stop, status))
                process.start()
                jobs.append((item, process, status))
            while any(p.is_alive() for _, p, _ in jobs):
                if args.stop_file and args.stop_file.exists():
                    stop.set()
                    break
                for _, process, status in jobs:
                    if process.is_alive() and status.exists():
                        try:
                            age = time.time()-json.loads(status.read_text())['heartbeat']
                            if age > args.worker_timeout:
                                process.terminate()
                        except (OSError, ValueError, KeyError):
                            pass
                time.sleep(.25)
        except KeyboardInterrupt:
            stop.set()
        finally:
            stop.set()
            deadline = time.monotonic()+args.shutdown_grace
            for _, process, _ in jobs:
                process.join(max(0, deadline-time.monotonic()))
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            for item in reserved:
                job = next((j for j in jobs if j[0]['id'] == item['id']), None)
                clean = job is None
                if job:
                    try:
                        clean = not job[1].is_alive() and json.loads(Path(str(job[2])+'.result').read_text())['clean']
                    except (OSError, ValueError, KeyError):
                        clean = False
                allocator.finalizar('web:'+item['id'], run_id, cleanup_ok=clean)
    failed = False
    for _, process, status in jobs:
        try:
            result = json.loads(Path(str(status)+'.result').read_text())
            failed |= process.exitcode != 0 or result['failed'] or not result['clean']
        except (OSError, ValueError, KeyError):
            failed = True
    return 2 if failed else 0
