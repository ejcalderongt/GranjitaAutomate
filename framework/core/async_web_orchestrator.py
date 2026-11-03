"""Worker web async opcional, sujeto al supervisor y reservas existentes."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from core.ai_agent import analizar_contenido_tiktok_async
from core.consent import gestionar_pantallas_previas_ue
from core.browser import ROOT, directorio_cuenta, iniciar_contexto_async, cerrar_contexto_async
from core.decision_telemetry import DecisionTelemetry
from core.scraper import extraer_contexto_video_movil


async def elemento_unico_async(page, selector):
    matches = page.locator(selector)
    visible = [matches.nth(i) for i in range(await matches.count()) if await matches.nth(i).is_visible()]
    if len(visible) != 1:
        raise ValueError('Se requiere exactamente un elemento visible')
    return visible[0]


async def ciclo_feed_async(page, account, selectors, client, *, telemetry, record, execute=False, warmup=False, stop=None,
        load_base=0, qa_db_path=None, run_id=None, ciclo_numero=1, proxy_ip=None, geo_provider='UNKNOWN'):
    from core.telemetry import DEFAULT_DB, inicializar_db_telemetria_async, registrar_metrica_ciclo_async
    cycle_id = uuid4().hex
    started = time.monotonic()
    metrics = {'latencia_dom':None,'latencia_openai':None,'tiempo_retencion':None,'estado_retencion':None,
               'espera_dom_visible_ms':None,'tiempo_retencion_programado_seg':None,'swipe_estado':'not_started'}
    phase = 'inicio'
    path = qa_db_path or DEFAULT_DB

    async def checkpoint(fase, estado='running', error=None):
        nonlocal phase
        phase = fase
        await registrar_metrica_ciclo_async(account,ciclo_numero,proxy_ip,geo_provider,db_path=path,
            run_id=run_id or telemetry.run_id,cycle_id=cycle_id,fase=fase,estado_ciclo=estado,error_log=error,
            duracion_total_ms=round((time.monotonic()-started)*1000,3),
            **{key:value for key,value in metrics.items() if key not in ('ai_failed','ai_error_type','cycle_warning_error')})
    try:
        if qa_db_path is None:
            await inicializar_db_telemetria_async(path)
        result = await _ciclo_feed_qa(page,account,selectors,client,telemetry=telemetry,record=record,
            execute=False,warmup=warmup,stop=stop,cycle_id=cycle_id,metrics=metrics,checkpoint=checkpoint,
            load_base=load_base,qa_db_path=path,run_id=run_id or telemetry.run_id)
        cycle_failed = metrics.get('ai_failed') or metrics.get('cycle_warning_error')
        await checkpoint('finalizado','cancelled' if result is None else 'passed' if result and not cycle_failed else 'failed',
                         metrics.get('ai_error_type') or metrics.get('cycle_warning_error'))
        return False if result is not None and cycle_failed else result
    except asyncio.CancelledError:
        try:
            await checkpoint(phase,'cancelled', 'CancelledError')
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            await checkpoint(phase,'failed',exc)
        except Exception:
            pass
        await record('QA ciclo fallido',cycle_id=cycle_id,ciclo_numero=ciclo_numero,fase=phase,error_type=type(exc).__name__)
        return False


async def _ciclo_feed_qa(page, account, selectors, client, *, telemetry, record, execute, warmup, stop,
        cycle_id, metrics, checkpoint, load_base, qa_db_path, run_id):
    from core.web_actions import ejecutar_desplazamiento_tactil
    from core.load_testing import regular_retencion_de_carga

    async def emit(event, **data):
        if event == 'Aviso':
            metrics['cycle_warning_error'] = data.get('error_type','Error')
        await asyncio.to_thread(telemetry.append, event, cycle_id=cycle_id, **data)
        await record(event, **data)

    async def evidence(stage):
        path = directorio_cuenta(ROOT/'logs', account)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'_'+stage+'.png')
        try:
            await page.screenshot(path=str(path))
            return True
        except Exception as exc:
            await emit('Aviso', stage=stage, error_type=type(exc).__name__)
            return False

    if await page.locator(selectors['login']).is_visible():
        await emit('Pendiente Cuenta')
        raise ValueError('Sesión requiere login manual')
    await elemento_unico_async(page, selectors['authenticated'])
    dom_wait_started = time.monotonic()
    await page.locator(selectors['active_video']).first.wait_for(state='visible',timeout=5000)
    active = await elemento_unico_async(page, selectors['active_video'])
    metrics['espera_dom_visible_ms'] = round((time.monotonic()-dom_wait_started)*1000,3)
    warnings = []
    dom_started = time.monotonic()
    metadata = await extraer_contexto_video_movil(page, scope=active, selectors=selectors.get('metadata'),
        aviso=lambda **data: warnings.append(data))
    metrics['latencia_dom'] = round((time.monotonic()-dom_started)*1000,3)
    await checkpoint('mapeo')
    for warning in warnings:
        await emit('metadata_warning', **warning)
    await emit('context', contexto=metadata, source='active_video_dom_async')
    has_description = metadata.get('descripcion','').strip() not in ('','Sin descripción')
    retention = (await regular_retencion_de_carga(metadata,load_base,stop) if has_description else
        {'tiempo_ejecutado':0,'estado_retencion':'completado','tiempo_programado':0})
    metrics.update(tiempo_retencion=retention['tiempo_ejecutado'],estado_retencion=retention['estado_retencion'],
                   tiempo_retencion_programado_seg=retention['tiempo_programado'])
    await checkpoint('retencion')
    await emit('qa_retention',**retention)
    if retention['estado_retencion'] == 'cancelado':
        return None
    await emit('Analizando con IA')
    await checkpoint('analisis')
    error = []
    started = time.perf_counter()
    result = (await analizar_contenido_tiktok_async('', metadata['descripcion'], datos_video=metadata,
        client=client,run_id=run_id,account_id=account,cycle_id=cycle_id,db_path=qa_db_path,
        on_error=error.append) if has_description else
        {'interactuar':False,'dar_like':False,'comentario':''})
    # Adaptación del contrato nuevo al registro histórico; no ejecuta acciones.
    decision = {'dar_like':result['interactuar'] and result['dar_like'], 'compartir':False,
                'comentar':bool(result['comentario']), 'comentario':result['comentario']}
    latency = round((time.perf_counter()-started)*1000,2)
    metrics['latencia_openai'] = latency
    metrics['latencia_ia_total_ms'] = latency
    if metadata.get('descripcion','').strip() in ('','Sin descripción'):
        metrics['latencia_openai'] = None
    elif hasattr(client,'last_api_latency_ms'):
        api_ms,admission_ms=client.last_api_latency_ms,getattr(client,'last_admission_latency_ms',None)
        metrics['latencia_openai'] = api_ms if isinstance(api_ms,(int,float)) else None
        metrics['latencia_admision_ms'] = admission_ms if isinstance(admission_ms,(int,float)) else None
    if stop is not None and stop.is_set():
        return None
    # Solo se persisten métricas puras, no la decisión ni el texto del feed.
    metrics['ai_failed'] = bool(error)
    metrics['ai_error_type'] = error[0] if error else None
    captured = await evidence('post_decision')
    if error:
        await emit('ai_error', error_type=error[0], latency_ms=latency)
    await emit('decision', decision=decision, contexto=metadata, latency_ms=latency,
        model='gpt-4o-mini', prompt_version='tiktok_text_qa_v1', evidencia=captured,
        decision_origin='fallback' if error else 'model' if metadata['descripcion'] not in ('', 'Sin descripción') else 'insufficient_context',
        execute_enabled=execute)
    await emit('read_only', execute_enabled=False)
    await checkpoint('pre_swipe')
    try:
        await ejecutar_desplazamiento_tactil(page)
        metrics['swipe_estado'] = 'sent'
        await evidence('post_swipe')
        await emit('Navegando')
        return True
    except Exception as exc:
        metrics['swipe_estado'] = 'failed'
        await emit('Aviso', stage='desplazamiento', error_type=type(exc).__name__)
        return False


async def worker_web_async(item, args, selectors, run_id, stop, status):
    from openai import AsyncOpenAI
    from core.async_api_admission import AsyncClienteRecuperable
    from core.database import Database
    from core.network_audit import verificar_proxy_auditable
    from config.proxies import ProxyAllocator
    from core.runtime_health import liberar_api
    name, token = item['id'], uuid4().hex
    runtime = context = bridge = None
    clean, failed = False, False
    db = Database()
    folder = directorio_cuenta(ROOT/'logs', name)
    audit = folder/(run_id+'.jsonl')
    telemetry = DecisionTelemetry(name, run_id)

    def write(event, data):
        with audit.open('a',encoding='utf-8') as file:
            file.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'event':event,**data},ensure_ascii=False)+'\n')
        temporary = Path(str(status)+'.tmp')
        temporary.write_text(json.dumps({'heartbeat':time.time(),'event':event}),encoding='utf-8')
        temporary.replace(status)

    async def record(event, **data):
        await asyncio.to_thread(write, event, data)

    try:
        await record('Inicio async')
        proxy = dict(item['proxy'])
        for key in ('username','password'):
            if os.getenv('PANDA_WEB_PROXY_'+key.upper()):
                proxy[key] = os.environ['PANDA_WEB_PROXY_'+key.upper()]
        runtime, context, page, bridge = await iniciar_contexto_async(item.get('profile',name), proxy,
            headless=args.web_headless, engine=args.web_engine)
        response = await page.goto('https://api.ipify.org', wait_until='domcontentloaded')
        if response is None or response.status != 200:
            raise ValueError('No se verificó la salida del proxy')
        observed = (await page.locator('body').inner_text()).strip()
        await asyncio.to_thread(verificar_proxy_auditable, db, ProxyAllocator(db),run_id,'web:'+name,item['proxy']['endpoint'],
            leer_configuracion=lambda:item['proxy']['endpoint'],consultar_salida=lambda:observed,
            expected_ip=item['proxy'].get('exit_ip'),alcance='Chromium async: petición HTTPS; no acredita tráfico del reproductor')
        await page.goto('https://www.tiktok.com/foryou', wait_until='domcontentloaded')
        await record('consentimiento_cookies',estado=await gestionar_pantallas_previas_ue(page,cancellation_event=stop))
        if args.web_login_only:
            while not stop.is_set() and not page.is_closed():
                await record('Autenticación manual')
                await asyncio.sleep(.5)
        else:
            async with AsyncOpenAI(timeout=25,max_retries=0) as api:
                client = AsyncClienteRecuperable(api, db, token,run_id,stop,args.rpm,args.api_concurrency,
                    heartbeat=lambda:record('Analizando con IA'))
                advanced = True
                for cycle in range(1,args.cycles+1):
                    if stop.is_set():
                        break
                    advanced = await ciclo_feed_async(page,name,selectors,client,telemetry=telemetry,record=record,
                        execute=args.execute and advanced,warmup=args.web_warmup,stop=stop,
                        load_base=args.web_load_base,qa_db_path=args.web_telemetry_db,run_id=run_id,
                        ciclo_numero=cycle,proxy_ip=observed)
                    if advanced is None:
                        await record('QA cancelado',ciclo_numero=cycle)
                        break
                    failed |= advanced is False
                    deadline = time.monotonic()+args.interval
                    while not stop.is_set() and time.monotonic() < deadline:
                        await asyncio.sleep(.1)
    except Exception as exc:
        failed = True
        await asyncio.to_thread(db.auditar_proxy,run_id,'web:'+name,item['proxy'].get('endpoint'),'ejecucion','fallido',
            error_tipo=type(exc).__name__,alcance='Web async: fallo de ejecución; consultar auditoría JSONL')
        await record('Error',error_type=type(exc).__name__)
    finally:
        if context is not None or runtime is not None or bridge is not None:
            clean = await cerrar_contexto_async(context,runtime,bridge)
        try:
            await asyncio.to_thread(liberar_api,db,token)
        except Exception as exc:
            clean, failed = False, True
            await record('Error de limpieza API',error_type=type(exc).__name__)
        await record('Finalizado',clean=clean,failed=failed)
        Path(str(status)+'.result').write_text(json.dumps({'clean':clean,'failed':failed}),encoding='utf-8')
