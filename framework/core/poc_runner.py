"""POC visible de una cuenta: DOM y métricas reales, sin acciones sociales."""
import asyncio
from dataclasses import dataclass
import ipaddress
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from core.browser import ROOT, validar_account_id, proxy_desde_entorno, opciones_proxy, iniciar_contexto_async, cerrar_contexto_async

log = logging.getLogger('qa.poc')


@dataclass(frozen=True)
class POCSettings:
    account_id: str = 'cuenta_tiktok_01'
    base_seconds: float = 6
    cycles: int = 5
    selectors_path: Path = ROOT/'config/web_selectors.mobile.json'
    require_europe: bool = True
    rotate_mobile: bool = False

    def validate(self):
        import math
        validar_account_id(self.account_id)
        if not math.isfinite(self.base_seconds) or not 0 <= self.base_seconds <= 30:
            raise ValueError('Base QA entre 0 y 30 segundos')
        if not 1 <= self.cycles <= 100:
            raise ValueError('Ciclos entre 1 y 100')
        if not self.selectors_path.is_file():
            raise ValueError('Archivo de selectores no encontrado')


async def ejecutar_poc(settings, stop, login_ready, notify, telemetry_db):
    from openai import AsyncOpenAI
    from core.async_api_admission import AsyncClienteRecuperable
    from core.async_web_orchestrator import ciclo_feed_async, elemento_unico_async
    from core.database import Database
    from core.decision_telemetry import DecisionTelemetry
    from core.mass_orchestrator import bloquear_granja
    from core.runtime_health import liberar_api
    from core.telemetry import listar_metricas, registrar_evento_poc_async
    from core.project_env import load_project_environment
    from tiktok_warmer.test_connection import resolver_geo_por_proxy
    settings.validate()
    run_id, token = 'poc-'+uuid4().hex, uuid4().hex
    runtime = context = bridge = db = None
    clean, failed = False, False
    guard = None
    guard_entered = False
    opening_attempted = False
    telemetry_saved = True
    mobile_manager = None
    stage = 'configuracion'
    await asyncio.to_thread(notify,'log','Preparando ejecución '+run_id)

    async def record(event, **data):
        notify('log',event + (' · '+data['error_type'] if data.get('error_type') else ''))
        if event in ('context','qa_retention','decision','Navegando'):
            try:
                notify('metrics',await asyncio.to_thread(listar_metricas,telemetry_db,run_id=run_id))
            except Exception:
                notify('log','Lectura de métricas temporalmente no disponible')

    async def audit(event, state, error=None):
        await registrar_evento_poc_async(run_id,settings.account_id,event,state,error=error,db_path=telemetry_db)

    try:
        guard = bloquear_granja(ROOT/'sessions/farm.lock')
        guard.__enter__()
        guard_entered = True
        await audit('admision','iniciado')
        if stop.is_set():
            await audit('parada_solicitada','cancelado')
            return
        load_project_environment()
        selectors = json.loads(settings.selectors_path.read_text(encoding='utf-8-sig'))
        if any(not selectors.get(key) or 'REEMPLAZAR' in selectors[key] for key in ('login','authenticated','active_video')):
            raise ValueError('Selectores de sesión/video pendientes')
        db = await asyncio.to_thread(Database)
        stage = 'proxy'
        notify('network',{'component':'proxy','state':'checking','message':'Comprobando salida del proxy…'})
        if settings.rotate_mobile:
            from config.proxies import ProxyManager
            mobile_manager = ProxyManager(telemetry_db=telemetry_db,run_id=run_id,
                account_id=settings.account_id,schema_initialized=True)
            notify('log','Preflight residencial: validando SOCKS5 sin API de rotación' if mobile_manager.mode=='rotating_residential'
                   else 'Smoke móvil: solicitando rotación y verificando cambio de salida antes de abrir el navegador')
            await mobile_manager.ejecutar_ciclo_rotacion_segura(stop)
            proxy = mobile_manager.browser_proxy()
        else:
            proxy = proxy_desde_entorno()
        if stop.is_set():
            await audit('parada_solicitada','cancelado')
            return
        opening_attempted = True
        runtime,context,page,bridge = await iniciar_contexto_async(settings.account_id,proxy,engine='patchright')
        await audit('navegador_listo','completado')
        notify('log','Patchright visible y puente local iniciados')
        verification_started = time.monotonic()
        response = await page.goto('https://api.ipify.org?format=json',wait_until='domcontentloaded')
        if response is None or response.status != 200:
            raise ConnectionError('No se verificó la salida HTTPS')
        observed = str(ipaddress.ip_address(json.loads(await page.locator('body').inner_text())['ip']))
        if mobile_manager is not None:
            await mobile_manager.validar_ip_navegador(observed,latencia_ms=(time.monotonic()-verification_started)*1000)
        notify('network',{'component':'proxy','state':'verified','message':'Salida HTTPS verificada en el navegador'})
        stage = 'geo'
        notify('network',{'component':'geo','state':'checking','message':'Verificando continente de salida…'})
        geo = await resolver_geo_por_proxy(observed,SimpleNamespace(bridge=bridge),opciones_proxy(proxy))
        notify('log','GeoIP: '+geo['provider_used']+' · continente '+geo['continente'])
        if settings.require_europe and geo['continente'] != 'EU':
            notify('log','GeoIP: salida EU no acreditada; TikTok todavía no se ha cargado')
            raise ValueError('La salida europea no está acreditada')
        notify('network',{'component':'geo','state':'verified' if settings.require_europe else 'info',
            'message':'Europa verificada' if settings.require_europe else 'Filtro desactivado · continente '+geo['continente']})
        stage = 'navegacion'
        await page.goto('https://www.tiktok.com/foryou',wait_until='domcontentloaded')
        from core.consent import gestionar_pantallas_previas_ue
        consent = await gestionar_pantallas_previas_ue(page,cancellation_event=stop)
        notify('log','Consentimiento de cookies: '+consent)
        await audit('esperando_login','en_espera')
        notify('login','Revisa la ventana del navegador y pulsa Continuar tras login')
        while not login_ready.is_set() and not stop.is_set() and not page.is_closed():
            await asyncio.sleep(.1)
        if stop.is_set() or page.is_closed():
            stop.set()
            await audit('parada_solicitada','cancelado')
            return
        await audit('continuacion_solicitada','completado')
        if await page.locator(selectors['login']).is_visible():
            raise ValueError('Login manual no completado')
        await elemento_unico_async(page,selectors['authenticated'])
        await audit('login_verificado','completado')
        logger = DecisionTelemetry(settings.account_id,run_id)
        async with AsyncOpenAI(timeout=25,max_retries=0) as api:
            client = AsyncClienteRecuperable(api,db,token,run_id,stop,30,1,heartbeat=lambda:record('Esperando admisión API'))
            for cycle in range(1,settings.cycles+1):
                if stop.is_set():
                    break
                notify('cycle',cycle)
                result = await ciclo_feed_async(page,settings.account_id,selectors,client,telemetry=logger,record=record,
                    execute=False,stop=stop,load_base=settings.base_seconds,qa_db_path=telemetry_db,
                    run_id=run_id,ciclo_numero=cycle,proxy_ip=observed,geo_provider=geo['provider_used'])
                failed |= result is False
                try:
                    rows = await asyncio.to_thread(listar_metricas,telemetry_db,run_id=run_id)
                    notify('metrics',rows)
                except Exception as exc:
                    notify('log','Lectura de métricas no disponible: '+type(exc).__name__)
                if result is None:
                    break
    except asyncio.CancelledError:
        stop.set()
        try:
            await audit('parada_solicitada','cancelado')
        except Exception:
            telemetry_saved = False
        notify('log','Cancelación recibida; cerrando recursos')
        raise
    except Exception as exc:
        failed = True
        if stage in ('proxy','geo'):
            notify('network',{'component':stage,'state':'failed','message':
                'No se pudo acreditar la salida europea. Revisa la región del proveedor.' if stage=='geo' and settings.require_europe
                else 'La comprobación de red no se completó. Revisa conexión y configuración.'})
        try:
            await audit('prueba_fallida','fallido',exc)
        except Exception:
            telemetry_saved = False
        from config.proxies import ProxyRotationError
        notify('log','Fallo de POC: '+(exc.code if isinstance(exc,ProxyRotationError) else type(exc).__name__))
    finally:
        async def finalize():
            nonlocal clean, failed, telemetry_saved
            clean = not opening_attempted
            if runtime is not None or context is not None or bridge is not None:
                clean = await cerrar_contexto_async(context,runtime,bridge)
            if db is not None:
                try:
                    await asyncio.to_thread(liberar_api,db,token)
                except Exception:
                    clean,failed = False,True
            if guard_entered:
                try:
                    guard.__exit__(None,None,None)
                except Exception:
                    clean,failed = False,True
            try:
                await audit('cierre_exitoso' if clean else 'cierre_fallido','completado' if clean else 'fallido')
            except Exception as exc:
                telemetry_saved,failed = False,True
                log.error('Cierre de recursos terminado; auditoría SQLite no confirmada (%s)',type(exc).__name__)
            try:
                notify('metrics',await asyncio.to_thread(listar_metricas,telemetry_db,run_id=run_id))
            except Exception:
                notify('log','Revisar la disponibilidad de SQLite para el informe final')
            notify('result',{'run_id':run_id,'clean':clean,'failed':failed,'cancelled':stop.is_set(),
                             'telemetry_saved':telemetry_saved})
        cleanup = asyncio.create_task(finalize())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise
