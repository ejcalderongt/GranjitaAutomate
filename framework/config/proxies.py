"""Proxies Android y web/m\xf3viles; estos controles no acreditan aislamiento VPN."""
import os
import re
import subprocess
import shutil
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import json
import ipaddress
import sqlite3
import asyncio
import contextlib


class ProxyRotationError(RuntimeError):
    """C\xf3digo controlado; nunca incluye URL, credenciales ni respuesta del proveedor."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ProxyManager:
    """Una instancia por worker. Control API directo y validaci\xf3n HTTPS por proxy."""
    def __init__(self, *, env_path=None, settings=None, telemetry_db=None, run_id=None,
                 account_id='network_qa', control_client=None, proxy_client=None, schema_initialized=False):
        import math
        from uuid import uuid4
        from urllib.parse import urlsplit
        from core.telemetry import DEFAULT_DB
        root=Path(__file__).resolve().parents[1]
        if settings is None:
            from dotenv import dotenv_values
            if env_path or os.getenv('PANDA_ENV_FILE'):
                values=dict(dotenv_values(env_path or os.environ['PANDA_ENV_FILE'],interpolate=False))
            else:
                values={**dotenv_values(root/'.env',interpolate=False),**dotenv_values(root/'tiktok_warmer/.env',interpolate=False)}
            values.update(os.environ)
        else:
            values=dict(settings)
        if any(key.startswith('PANDA_PROXY_') for key in values):
            values.update(self._normalizar_panda(values))
        self.telemetry_db=Path(telemetry_db or DEFAULT_DB)
        self.run_id,self.account_id=run_id or 'network-'+uuid4().hex,account_id
        self._control_client,self._proxy_client=control_client,proxy_client
        self._schema_ready=schema_initialized
        self._rotating=False
        self._expected_ip=None
        self._rotation_url=(values.get('PROXY_ROTATION_URL') or '').strip()
        self._allow_local_http=values.get('PROXY_ROTATION_ALLOW_LOCAL_HTTP')=='1'
        try:
            self.mode=(values.get('PROXY_MODE') or 'mobile_api').strip().lower()
            self.provider=(values.get('PROXY_PROVIDER') or 'generic').strip().lower().replace('-','_')
            if self.mode not in ('mobile_api','rotating_residential'):
                raise ProxyRotationError('proxy_mode_invalid')
            self.wait_seconds=float(values.get('PROXY_ROTATION_WAIT_SECONDS','10'))
            if not math.isfinite(self.wait_seconds) or not 0 <= self.wait_seconds <= 30:
                raise ValueError()
            url=values.get('PROXY_URL','')
            if values.get('PROXY_HOST') or values.get('PROXY_PORT'):
                host,port=values.get('PROXY_HOST'),values.get('PROXY_PORT')
                if not host or not port or any(c in host for c in '/@?#'):
                    raise ValueError()
                if ':' in host and not host.startswith('['):
                    host='['+host+']'
                scheme=values.get('PROXY_PROTOCOL') or urlsplit(url).scheme or 'http'
                url=f'{scheme}://{host}:{port}'
            if values.get('PROXY_USER') or values.get('PROXY_PASS'):
                user,password=values.get('PROXY_USER'),values.get('PROXY_PASS')
            else:
                user,password=values.get('PROXY_USERNAME'),values.get('PROXY_PASSWORD')
            from tiktok_warmer.core.browser import configurar_proxy
            self._proxy=configurar_proxy(url,user,password)
            if self.provider=='proxy_cheap' and self.mode=='rotating_residential' and not self._proxy['server'].startswith('socks5://'):
                raise ProxyRotationError('proxy_cheap_requires_socks5')
            if self._proxy.get('password')=='MI_CONTRASENA_REAL':
                raise ValueError()
        except (ValueError,TypeError):
            raise ProxyRotationError('proxy_configuration_invalid') from None

    def browser_proxy(self):
        return dict(self._proxy)

    async def contar_salidas_distintas(self, *, muestras: int, timeout: float) -> dict:
        """Read public exits in memory only; no audit, database or retry layer."""
        import math
        import httpx
        import logging
        if type(muestras) is not int or not 1 <= muestras <= 32:
            raise ValueError('Muestras fuera de rango')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 60:
            raise ValueError('Timeout fuera de rango')
        try:
            options = self.browser_proxy()
            if not options.get('server'):
                raise ValueError()
            if bool(options.get('username')) != bool(options.get('password')):
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            raise ValueError('Proxy no configurado') from None

        async def sample():
            injected = getattr(self, '_proxy_client', None)
            if injected is not None:
                response = await injected.get('https://api.ipify.org?format=json', timeout=timeout)
            else:
                auth = (options['username'], options['password']) if options.get('username') else None
                async with httpx.AsyncClient(proxy=httpx.Proxy(options['server'], auth=auth),
                        timeout=timeout, trust_env=False, follow_redirects=False,
                        limits=httpx.Limits(max_keepalive_connections=0)) as client:
                    response = await client.get('https://api.ipify.org?format=json')
            if response.status_code != 200:
                raise ValueError()
            address = ipaddress.ip_address(response.json()['ip'])
            if not address.is_global:
                raise ValueError()
            return str(address)

        exits = set()
        result = {'distinct': 0, 'total': 0, 'errors': 0, 'timeouts': 0}
        quiet = [logging.getLogger(name) for name in ('httpx', 'httpcore')]
        states = [logger.disabled for logger in quiet]
        for logger in quiet:
            logger.disabled = True
        try:
            for _ in range(muestras):
                try:
                    exits.add(await asyncio.wait_for(sample(), timeout=timeout))
                except (asyncio.TimeoutError, httpx.TimeoutException):
                    result['timeouts'] += 1
                except Exception:
                    result['errors'] += 1
                result['total'] += 1
        finally:
            for logger, state in zip(quiet, states):
                logger.disabled = state
        result['distinct'] = len(exits)
        return result

    @staticmethod
    def _normalizar_panda(values):
        # PROXY_SCHEME/PROTOCOL, HOST, PORT, USER/USERNAME, PASS/PASSWORD, COUNTRY migrate to PANDA_PROXY_*.
        def field(name):
            key='PANDA_PROXY_'+name
            return values[key] if key in values else values.get('PROXY_'+name)
        fields=[field(name) for name in ('SCHEME','HOST','PORT','USER','PASS')]
        if not any(value is not None and value!='' for value in fields):
            raise ValueError('Proxy no configurado')
        try:
            scheme,host,port,user,password=fields
            if not all(isinstance(value,str) and value for value in fields):
                raise ValueError()
            if scheme not in ('socks5','socks5h','http','https') or not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',host):
                raise ValueError()
            if not port.isascii() or not port.isdigit() or not 1<=int(port)<=65535:
                raise ValueError()
            if ':' in user or any(ord(c)<32 or ord(c)>126 for c in user+password):
                raise ValueError()
            country=field('COUNTRY') or ''
            if not isinstance(country,str) or country and not re.fullmatch(r'[A-Za-z]{2}',country):
                raise ValueError()
            mode=values.get('PANDA_PROXY_SESSION_MODE','rotating')
            if mode not in ('rotating','sticky'):
                raise ValueError()
            if mode=='sticky':
                ttl=values.get('PANDA_PROXY_SESSION_TTL','')
                if not isinstance(ttl,str) or not ttl.isdigit() or not 1<=int(ttl)<=86400:
                    raise ValueError()
            return {'PROXY_URL':'','PROXY_HOST':host,'PROXY_PORT':port,'PROXY_USER':user,
                    'PROXY_PASS':password,'PROXY_PROTOCOL':'socks5' if scheme=='socks5h' else scheme,'PROXY_MODE':'rotating_residential'}
        except (ValueError,TypeError):
            raise ValueError('Proxy invalido') from None

    @classmethod
    def desde_panda(cls,settings=None):
        """Root configuration only; credentials remain opaque and unchanged."""
        if settings is None:
            from dotenv import dotenv_values
            root=Path(__file__).resolve().parents[1]
            settings=dict(dotenv_values(os.getenv('PANDA_ENV_FILE') or root/'.env',interpolate=False))
            settings.update(os.environ)
        normalized=cls._normalizar_panda(settings)
        try:
            manager=cls(settings=normalized)
        except Exception:
            raise ValueError('Proxy invalido') from None
        manager._panda_country=(settings.get('PANDA_PROXY_COUNTRY')
            if 'PANDA_PROXY_COUNTRY' in settings else settings.get('PROXY_COUNTRY')) or ''
        return manager

    async def endpoint_para_chromium(self):
        """Return existing bridge options and resource; caller must close resource."""
        from tiktok_warmer.core.socks_bridge import proxy_para_chromium
        pending=asyncio.create_task(asyncio.to_thread(proxy_para_chromium,self.browser_proxy()))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            _,bridge=await pending
            if bridge is not None:
                await asyncio.to_thread(bridge.close)
            raise

    @classmethod
    async def verificar_preflight(cls,*,run_id):
        """Isolated Patchright verification; no Panda, Android or SQLite calls."""
        import logging
        import httpx
        import time
        from types import SimpleNamespace
        from core.browser import ROOT,iniciar_contexto_async,cerrar_contexto_async
        from core.geo_resolver import obtener_geolocalizacion_con_bypass
        logger=logging.getLogger('qa.panda.masivo')
        try:
            manager=cls.desde_panda()
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id):
                raise ValueError('Proxy invalido')
        except ValueError:
            logger.error('proxy_preflight_config valid=false duration_ms=0')
            logger.error('Proxy no verificable')
            raise
        runtime=context=bridge=browser_bridge=None
        verified=False;cancelled=False;clean=True
        bridge_closed=True
        cause='unknown';stage='direct_ipify';started=time.monotonic()
        ip_url='https://ipv4.icanhazip.com'
        ip_timeout=25.0
        failure_type='none'
        proxy_auth_rejected=False
        sessions=(ROOT/'sessions'/('preflight-'+run_id)).resolve()
        quiet=[logging.getLogger(name) for name in ('httpx','httpcore','pproxy','warmer.geo')]
        disabled=[item.disabled for item in quiet]
        for item in quiet:
            item.disabled=True

        def public_ip(value):
            if not isinstance(value,str):
                raise ValueError()
            parsed=ipaddress.ip_address(value.strip())
            if not parsed.is_global:
                raise ValueError()
            return str(parsed)

        async def cleanup():
            nonlocal bridge_closed
            result=True
            try:
                if runtime is not None or context is not None or browser_bridge is not None:
                    result=await cerrar_contexto_async(context,runtime,browser_bridge,close_timeout=5)
            except Exception:
                result=False
            finally:
                if bridge is not None:
                    try:
                        # Also confirm closure when browser cleanup owns this bridge.
                        await asyncio.to_thread(bridge.close)
                    except Exception:
                        bridge_closed=False
                        result=False
            logger.info('proxy_preflight_cleanup bridge_closed=%s duration_ms=%d',
                        str(bridge_closed).lower(),round((time.monotonic()-started)*1000))
            # Delete only the unique temporary directory created for this run.
            if result and sessions.exists() and sessions.parent==(ROOT/'sessions').resolve():
                try:
                    await asyncio.to_thread(shutil.rmtree,sessions)
                except OSError:
                    result=False
            return result

        try:
            with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
                try:
                    async with httpx.AsyncClient(timeout=ip_timeout,trust_env=False,follow_redirects=False) as direct:
                        response=await direct.get(ip_url,timeout=ip_timeout)
                        if response.status_code!=200:
                            raise ValueError()
                        try:
                            host_ip=public_ip(response.text)
                        except ValueError:
                            # Preserve support for clients that return a JSON IP envelope.
                            host_ip=public_ip(response.json().get('ip'))
                    stage='bridge'
                    options,bridge=await manager.endpoint_para_chromium()
                    stage='browser_start'
                    runtime,context,page,browser_bridge=await asyncio.wait_for(iniciar_contexto_async(
                        'preflight-proxy',options,headless=True,sessions_root=sessions,engine='patchright'),timeout=15)
                    stage='ipify'
                    response=await page.goto(ip_url,wait_until='domcontentloaded',timeout=ip_timeout*1000)
                    if response is None or response.status!=200:
                        cause='provider'
                        raise ValueError()
                    observed=public_ip(await page.locator('body').inner_text(timeout=5000))
                    if observed==host_ip:
                        cause='leak'
                        raise ValueError()
                    stage='geoip'
                    auth = (options['username'], options['password']) if options.get('username') else None
                    async with httpx.AsyncClient(proxy=httpx.Proxy(options['server'], auth=auth),timeout=5,
                            trust_env=False,follow_redirects=False) as proxied:
                        async def get_geo(*args, **kwargs):
                            nonlocal proxy_auth_rejected
                            try:
                                response = await proxied.get(*args, **kwargs)
                            except httpx.ProxyError as exc:
                                # HTTP CONNECT rejection arrives as an exception.
                                proxy_auth_rejected |= bool(re.match(r'^407(?:\s|$)', str(exc)))
                                raise
                            proxy_auth_rejected |= response.status_code == 407
                            return response
                        async with asyncio.timeout(12):
                            geo=await obtener_geolocalizacion_con_bypass(observed,cliente_http=SimpleNamespace(get=get_geo))
                    if geo.get('geo_status')!='resolved':
                        if proxy_auth_rejected:
                            cause='auth_407'
                        elif any(a.get('error_type') in ('ReadTimeout','TimeoutError') for a in geo.get('attempts',[])):
                            cause='timeout_geoip'
                        else:
                            cause='geoip_unavailable'
                        raise ValueError()
                    if manager._panda_country and geo.get('pais')!=manager._panda_country.upper():
                        cause='geoip_country_mismatch'
                        raise ValueError()
                    verified=True
                except asyncio.CancelledError:
                    cancelled=True
                except Exception as exc:
                    failure_type=type(exc).__name__
                    if cause=='unknown':
                        if isinstance(exc,(httpx.TimeoutException,TimeoutError)) or type(exc).__name__=='TimeoutError':
                            cause='timeout_geoip' if stage=='geoip' else 'timeout_ipify' if stage in ('ipify','direct_ipify') else 'bridge'
                        else:
                            cause='bridge' if stage in ('bridge','browser_start') else 'provider'
                    verified=False
                finally:
                    task=asyncio.create_task(cleanup())
                    try:
                        clean=await asyncio.shield(task)
                    except asyncio.CancelledError:
                        cancelled=True
                        clean=await task
        finally:
            for item,state in zip(quiet,disabled):
                item.disabled=state
        if cancelled:
            raise asyncio.CancelledError() from None
        if not verified or not clean:
            if verified and not clean:
                cause='bridge'
                stage='cleanup'
            logger.error('proxy_preflight_trace stage=%s cause=%s error_type=%s',
                         stage,cause,failure_type)
            logger.error('proxy_preflight_%s verified=%s bridge_closed=%s duration_ms=%d',
                         cause,str(verified).lower(),str(bridge_closed).lower(),round((time.monotonic()-started)*1000))
            logger.error('Proxy no verificable')
            raise RuntimeError('Proxy no verificable') from None
        logger.info('Proxy verificado')

    async def _prepare(self):
        if not self._schema_ready:
            from core.telemetry import inicializar_db_telemetria_async
            await inicializar_db_telemetria_async(self.telemetry_db)
            self._schema_ready=True

    async def _audit(self,operation,action,phase,state,**metrics):
        from core.telemetry import registrar_evento_red_async
        await registrar_evento_red_async(self.run_id,self.account_id,operation,action,phase,state,
            db_path=self.telemetry_db,proxy_endpoint=self._proxy['server'],modo=self.mode,**metrics)

    async def _get(self,client,url,cancellation_event):
        import asyncio
        if cancellation_event is not None and cancellation_event.is_set():
            raise asyncio.CancelledError()
        async def wait_cancel():
            if isinstance(cancellation_event,asyncio.Event):
                await cancellation_event.wait()
            else:
                while not cancellation_event.is_set():
                    await asyncio.sleep(.05)
        request=asyncio.create_task(client.get(url,timeout=10,follow_redirects=False))
        watcher=asyncio.create_task(wait_cancel()) if cancellation_event is not None else None
        try:
            async with asyncio.timeout(10):
                if watcher is not None:
                    done,_=await asyncio.wait((request,watcher),return_when=asyncio.FIRST_COMPLETED)
                    if watcher in done:
                        raise asyncio.CancelledError()
                return await request
        finally:
            for task in (request,watcher):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (request,watcher) if task is not None),return_exceptions=True)

    async def obtener_ip_publica(self,cancellation_event=None,*,fase='preflight',operation_id=None,
                                 expected_ip=None,previous_ref=None):
        import asyncio
        import hashlib
        import time
        import httpx
        from contextlib import AsyncExitStack
        from uuid import uuid4
        await self._prepare()
        operation=operation_id or uuid4().hex
        await self._audit(operation,'validacion',fase,'iniciado')
        started=time.monotonic();status=None
        try:
            async with AsyncExitStack() as stack:
                client=self._proxy_client
                if client is None:
                    auth=(self._proxy['username'],self._proxy['password']) if self._proxy.get('username') else None
                    client=await stack.enter_async_context(httpx.AsyncClient(proxy=httpx.Proxy(self._proxy['server'],auth=auth),
                        timeout=10,trust_env=False,follow_redirects=False))
                response=await self._get(client,'https://api.ipify.org?format=json',cancellation_event)
                status=response.status_code
                if status != 200:
                    raise ProxyRotationError('proxy_http_'+str(status))
                data=response.json()
                if not isinstance(data,dict) or not isinstance(data.get('ip'),str):
                    raise ProxyRotationError('proxy_response_invalid')
                address=ipaddress.ip_address(data['ip'])
                if not address.is_global:
                    raise ProxyRotationError('proxy_ip_not_public')
                observed=str(address)
                if expected_ip is not None and observed != expected_ip:
                    raise ProxyRotationError('browser_ip_mismatch')
                if previous_ref and hashlib.sha256(observed.encode()).hexdigest()==previous_ref:
                    raise ProxyRotationError('ip_unchanged')
        except asyncio.CancelledError:
            await self._audit(operation,'validacion',fase,'cancelado',latencia_ms=(time.monotonic()-started)*1000)
            raise
        except Exception as exc:
            code=exc.code if isinstance(exc,ProxyRotationError) else 'proxy_timeout' if isinstance(exc,(TimeoutError,httpx.TimeoutException)) else 'proxy_transport_error' if isinstance(exc,httpx.RequestError) else 'proxy_dependency_error' if isinstance(exc,ImportError) else 'proxy_response_invalid'
            await self._audit(operation,'validacion',fase,'fallido',latencia_ms=(time.monotonic()-started)*1000,
                http_status=status,error_codigo=code,cambio_ip=False if code=='ip_unchanged' else None)
            raise ProxyRotationError(code) from None
        await self._audit(operation,'validacion',fase,'verificado',latencia_ms=(time.monotonic()-started)*1000,
            http_status=status,ip_nueva=observed,cambio_ip=True if previous_ref else None)
        return observed

    def _validate_rotation_url(self):
        # El residencial no tiene URL de control: ni siquiera se valida.
        if self.mode=='rotating_residential':
            return
        from urllib.parse import urlsplit
        if not self._rotation_url:
            raise ProxyRotationError('rotation_url_missing')
        try:
            parsed=urlsplit(self._rotation_url)
            if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError()
            parsed.port
            if parsed.scheme=='https':
                return
            if parsed.scheme=='http' and self._allow_local_http:
                if parsed.hostname=='localhost' or ipaddress.ip_address(parsed.hostname).is_private:
                    return
        except ValueError:
            pass
        raise ProxyRotationError('rotation_url_requires_https')

    async def rotar_ip_movil(self,cancellation_event=None):
        # Compatibilidad con llamadores antiguos: este nombre no debe activar
        # webhooks ni bloquear un perfil residencial ya configurado.
        if self.mode=='rotating_residential':
            return await self.preparar_conexion(cancellation_event)
        import asyncio
        import hashlib
        import time
        import httpx
        from contextlib import AsyncExitStack
        from uuid import uuid4
        from core.load_testing import regular_retencion_de_carga
        from core.telemetry import ultima_ip_validada_ref
        await self._prepare()
        operation=uuid4().hex
        await self._audit(operation,'rotacion','inicio','iniciado')
        if self._rotating:
            await self._audit(operation,'rotacion','inicio','fallido',error_codigo='rotation_in_progress')
            raise ProxyRotationError('rotation_in_progress')
        self._rotating=True
        self._expected_ip=None
        started=time.monotonic();request_ms=None;status=None
        try:
            if self.mode!='mobile_api':
                raise ProxyRotationError('rotation_api_not_applicable')
            self._validate_rotation_url()
            if cancellation_event is not None and cancellation_event.is_set():
                raise asyncio.CancelledError()
            previous_ref=await asyncio.to_thread(ultima_ip_validada_ref,self.account_id,self._proxy['server'],db_path=self.telemetry_db)
            if previous_ref is None:
                baseline=await self.obtener_ip_publica(cancellation_event,fase='baseline',operation_id=operation)
                previous_ref=hashlib.sha256(baseline.encode()).hexdigest()
            async with AsyncExitStack() as stack:
                client=self._control_client
                if client is None:
                    client=await stack.enter_async_context(httpx.AsyncClient(timeout=10,trust_env=False,follow_redirects=False))
                request_started=time.monotonic()
                try:
                    response=await self._get(client,self._rotation_url,cancellation_event)
                finally:
                    request_ms=(time.monotonic()-request_started)*1000
                status=response.status_code
                if not 200 <= status < 300:
                    raise ProxyRotationError('rotation_http_'+str(status))
                try:
                    payload=response.json()
                except ValueError:
                    payload=None
                if isinstance(payload,dict) and (payload.get('success') is False or payload.get('error') or payload.get('status') in ('fail','error','failed')):
                    raise ProxyRotationError('rotation_provider_rejected')
            await self._audit(operation,'rotacion','control_api','solicitado',latencia_ms=request_ms,http_status=status)
            waiting=await regular_retencion_de_carga({},self.wait_seconds,cancellation_event)
            if waiting['estado_retencion']=='cancelado':
                raise asyncio.CancelledError()
            observed=await self.obtener_ip_publica(cancellation_event,fase='post_rotacion',operation_id=operation,previous_ref=previous_ref)
            await self._audit(operation,'rotacion','final','verificado',latencia_ms=request_ms,
                latencia_total_ms=(time.monotonic()-started)*1000,http_status=status,cambio_ip=True,ip_nueva=observed)
            self._expected_ip=observed
            return observed
        except asyncio.CancelledError:
            await self._audit(operation,'rotacion','final','cancelado',latencia_ms=request_ms,
                latencia_total_ms=(time.monotonic()-started)*1000,http_status=status,error_codigo='rotation_cancelled_state_unknown')
            raise
        except Exception as exc:
            code=exc.code if isinstance(exc,ProxyRotationError) else 'rotation_timeout' if isinstance(exc,(TimeoutError,httpx.TimeoutException)) else 'rotation_transport_error' if isinstance(exc,httpx.RequestError) else 'rotation_internal_error'
            await self._audit(operation,'rotacion','final','fallido',latencia_ms=request_ms,
                latencia_total_ms=(time.monotonic()-started)*1000,http_status=status,
                cambio_ip=False if code=='ip_unchanged' else None,error_codigo=code)
            raise ProxyRotationError(code) from None
        finally:
            self._rotating=False

    async def ejecutar_ciclo_rotacion_segura(self,cancellation_event=None):
        return await self.preparar_conexion(cancellation_event)

    async def preparar_conexion(self,cancellation_event=None):
        """Residencial aleatorio: validar salida, sin webhooks ni IP nueva forzada."""
        if self.mode=='mobile_api':
            return await self.rotar_ip_movil(cancellation_event)
        observed=await self.obtener_ip_publica(cancellation_event,fase='residencial_preflight')
        self._expected_ip=None
        return observed

    async def validar_ip_navegador(self,observed,*,latencia_ms=None):
        from uuid import uuid4
        await self._prepare()
        operation=uuid4().hex
        if self.mode=='rotating_residential':
            try:
                address=ipaddress.ip_address(observed)
                if not address.is_global:
                    raise ValueError()
            except ValueError:
                await self._audit(operation,'validacion','navegador','fallido',latencia_ms=latencia_ms,error_codigo='proxy_ip_not_public')
                raise ProxyRotationError('proxy_ip_not_public') from None
            await self._audit(operation,'validacion','navegador','verificado',latencia_ms=latencia_ms,ip_nueva=str(address))
            return
        if self._expected_ip is None or observed != self._expected_ip:
            await self._audit(operation,'validacion','navegador','fallido',latencia_ms=latencia_ms,error_codigo='browser_ip_mismatch')
            raise ProxyRotationError('browser_ip_mismatch')
        await self._audit(operation,'validacion','navegador','verificado',latencia_ms=latencia_ms,ip_nueva=observed)

_adb_server = ContextVar('adb_server',default=None)


def servidor_adb_actual():
    return _adb_server.get()


@contextmanager
def usar_servidor_adb(host,port):
    token=_adb_server.set((host,int(port)))
    try:
        yield
    finally:
        _adb_server.reset(token)


class ADBError(RuntimeError):
    """ADB ausente, inaccesible o comando Android fallido."""


def verificar_adb():
    override = os.getenv('ADB_PATH')
    native_config=Path(__file__).resolve().parents[1]/'config/native_dependencies.local.json'
    if not override and native_config.is_file():
        override=json.loads(native_config.read_text(encoding='utf-8'))['adb_path']
    if override:
        binary = shutil.which(override)
        if not binary:
            raise ADBError(f'ADB_PATH apunta a un ejecutable inexistente o inaccesible: {override}. '
                           'Corrige ADB_PATH/config/native_dependencies.local.json o instala Platform-Tools.')
        return binary
    executable = 'adb.exe' if os.name == 'nt' else 'adb'
    candidates = ['adb', str(Path(__file__).resolve().parents[1]/'tools'/'platform-tools'/executable)]
    for name in ('ANDROID_HOME','ANDROID_SDK_ROOT'):
        if os.getenv(name):
            candidates.append(str(Path(os.environ[name])/'platform-tools'/executable))
    if os.getenv('LOCALAPPDATA'):
        candidates.append(str(Path(os.environ['LOCALAPPDATA'])/'Android'/'Sdk'/'platform-tools'/executable))
    for candidate in candidates:
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise ADBError(
        'No se encontr\xf3 ADB. Descarga Platform-Tools para Windows desde '
        'https://developer.android.com/tools/releases/platform-tools y extrae la carpeta '
        'platform-tools dentro de tools/ del proyecto. Tambi\xe9n puedes agregarla al PATH '
        'o definir ADB_PATH con la ruta absoluta a adb.exe.')


def adb(*args, timeout=20):
    binary = verificar_adb()
    server=servidor_adb_actual()
    prefix=[]
    if server:
        if '-H' in args or '-P' in args:
            raise ValueError('No se permite cambiar el servidor dentro de una sesi\xf3n ADB fijada')
        prefix=['-H',server[0],'-P',str(server[1])]
    environment=os.environ.copy()
    if server or '-H' in args or '-P' in args:
        for name in ('ADB_SERVER_SOCKET','ANDROID_ADB_SERVER_ADDRESS','ANDROID_ADB_SERVER_PORT'):
            environment.pop(name,None)
    try:
        return subprocess.run([binary,*prefix,*args], check=True,
            capture_output=True, text=True, timeout=timeout, encoding='utf-8',
            errors='replace',env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0).stdout.strip()
    except subprocess.TimeoutExpired as exc:
        raise ADBError('Timeout ADB: comprueba cable, hub, alimentaci\xf3n y autorizaci\xf3n USB') from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or '').strip()[:500]
        raise ADBError(f'Fall\xf3 ADB/Android: {detail}. Comprueba adb devices -l y autorizaci\xf3n USB') from exc
    except OSError as exc:
        raise ADBError(f'No se pudo ejecutar adb.exe: {exc}') from exc


def validar_proxy(host, port):
    if not re.fullmatch(r'[a-zA-Z0-9.-]+', host) or not 1 <= int(port) <= 65535:
        raise ValueError('Proxy requiere hostname/IPv4 y puerto v\xe1lido, sin credenciales')
    return f'{host}:{int(port)}'


def configurar_proxy_dispositivo(device_id, ip_proxy, puerto_proxy):
    value = validar_proxy(ip_proxy, puerto_proxy)
    adb('-s', device_id, 'shell', 'settings', 'put', 'global', 'http_proxy', value)
    if adb('-s', device_id, 'shell', 'settings', 'get', 'global', 'http_proxy') != value:
        raise ADBError('Android no confirm\xf3 el proxy')


def limpiar_proxy_dispositivo(device_id):
    adb('-s', device_id, 'shell', 'settings', 'put', 'global', 'http_proxy', ':0')
    if adb('-s', device_id, 'shell', 'settings', 'get', 'global', 'http_proxy') != ':0':
        raise ADBError('Android no confirm\xf3 limpieza de proxy')


def leer_proxy_pool(path):
    if not Path(path).exists():
        return []
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('proxies'),list):
        raise ValueError('proxy_pool.json requiere un objeto con lista proxies')
    mode=data.get('mode','production')
    if mode not in ('production','laboratory'):
        raise ValueError('Modo de red inv\xe1lido')
    laboratory=mode=='laboratory'
    try:
        lab_host=str(ipaddress.IPv4Address(data['lab_host'])) if laboratory else None
    except (KeyError,ValueError) as exc:
        raise ValueError('El modo laboratorio requiere lab_host IPv4 privado') from exc
    if laboratory and not lab_host.startswith(('10.','192.168.')) and not ipaddress.IPv4Address(lab_host) in ipaddress.ip_network('172.16.0.0/12'):
        raise ValueError('El proxy de laboratorio debe estar en una red IPv4 privada RFC1918')
    result=[]
    for item in data['proxies']:
        if not isinstance(item,dict) or not isinstance(item.get('host'),str) or 'port' not in item:
            raise ValueError('Cada proxy requiere host IPv4 y port')
        host=str(ipaddress.IPv4Address(item['host']))
        if laboratory and host!=lab_host:
            raise ValueError('Todos los endpoints de laboratorio deben usar lab_host')
        try:
            port=int(item['port'])
        except (TypeError,ValueError) as exc:
            raise ValueError('Puerto de proxy inv\xe1lido') from exc
        endpoint=validar_proxy(host,port)
        exit_ip=str(ipaddress.ip_address(item['exit_ip'])) if item.get('exit_ip') else None
        result.append({'endpoint':endpoint,'host':host,'port':port,'exit_ip':exit_ip,
                       'enabled':bool(item.get('enabled',True))})
        if laboratory:
            result[-1]['lab_shared_exit']=True
    if len({x['endpoint'] for x in result})!=len(result):
        raise ValueError('Endpoints duplicados en proxy_pool.json')
    return result


class ProxyAllocator:
    """Reservas duraderas, sin expiraci\xf3n autom\xe1tica tras un crash o p\xe9rdida de USB."""
    def __init__(self,database):
        self.database=database

    def sincronizar(self,entries):
        with self.database.conexion() as con:
            con.execute('BEGIN IMMEDIATE')
            modes={bool(item.get('lab_shared_exit',False)) for item in entries}
            if len(modes)>1:
                raise ValueError('No se pueden mezclar laboratorio y producci\xf3n en el mismo pool')
            if modes and con.execute('''SELECT 1 FROM proxy_reservas r JOIN proxy_pool p ON r.endpoint=p.endpoint
                WHERE p.lab_shared_exit!=? LIMIT 1''',(int(next(iter(modes))),)).fetchone():
                raise ValueError('Cerrar y limpiar las reservas antes de cambiar el modo de red')
            con.execute('UPDATE proxy_pool SET habilitado=0')
            for item in entries:
                old=con.execute('''SELECT p.lab_shared_exit FROM proxy_pool p WHERE p.endpoint=?
                    AND EXISTS(SELECT 1 FROM proxy_reservas r WHERE r.endpoint=p.endpoint)''',(item['endpoint'],)).fetchone()
                if old and bool(old['lab_shared_exit'])!=bool(item.get('lab_shared_exit',False)):
                    raise ValueError('No se puede cambiar de modo un endpoint con reserva activa o en cuarentena')
                con.execute('''INSERT INTO proxy_pool(endpoint,host,puerto,exit_ip,habilitado,lab_shared_exit) VALUES (?,?,?,?,?,?)
                    ON CONFLICT(endpoint) DO UPDATE SET host=excluded.host,puerto=excluded.puerto,
                    exit_ip=excluded.exit_ip,habilitado=excluded.habilitado,lab_shared_exit=excluded.lab_shared_exit''',
                    (item['endpoint'],item['host'],item['port'],item.get('exit_ip'),int(item.get('enabled',True)),int(item.get('lab_shared_exit',False))))

    def reservar(self,device_id,run_id,endpoint=None):
        from core.database import ahora
        with self.database.conexion() as con:
            con.execute('BEGIN IMMEDIATE')
            binding=con.execute('SELECT endpoint FROM proxy_perfiles WHERE account_id=?',(device_id,)).fetchone()
            if binding:
                if endpoint is not None and endpoint!=binding['endpoint']:
                    return None
                endpoint=binding['endpoint']
            existing=con.execute('SELECT * FROM proxy_reservas WHERE id_adb=?',(device_id,)).fetchone()
            if existing:
                if existing['run_id']!=run_id or existing['estado']!='activo':
                    return None
                row=con.execute('SELECT * FROM proxy_pool WHERE endpoint=?',(existing['endpoint'],)).fetchone()
                return dict(row) if endpoint is None or row['endpoint']==endpoint else None
            row=con.execute('''SELECT p.* FROM proxy_pool p WHERE habilitado=1
                AND (? NOT LIKE 'web:%' OR NOT EXISTS(SELECT 1 FROM proxy_perfiles b WHERE b.endpoint=p.endpoint AND b.account_id!=?))
                AND NOT EXISTS(SELECT 1 FROM proxy_reservas r WHERE r.endpoint=p.endpoint
                    OR r.identidad=CASE WHEN p.lab_shared_exit=1 THEN 'lab:'||p.endpoint ELSE COALESCE(p.exit_ip,p.endpoint) END)
                AND (? IS NULL OR p.endpoint=?) ORDER BY p.endpoint LIMIT 1''',(device_id,device_id,endpoint,endpoint)).fetchone()
            if not row:
                return None
            con.execute('INSERT INTO proxy_reservas VALUES (?,?,?,?,?,?)',
                (row['endpoint'],'lab:'+row['endpoint'] if row['lab_shared_exit'] else row['exit_ip'] or row['endpoint'],device_id,run_id,ahora(),'activo'))
            return dict(row)

    def validar(self,device_id,run_id,endpoint):
        with self.database.conexion() as con:
            return con.execute('''SELECT 1 FROM proxy_reservas WHERE id_adb=? AND run_id=?
                AND endpoint=? AND estado='activo' ''',(device_id,run_id,endpoint)).fetchone() is not None

    def disponibles(self):
        with self.database.conexion() as con:
            return con.execute('''SELECT COUNT(DISTINCT CASE WHEN p.lab_shared_exit=1 THEN 'lab:'||p.endpoint ELSE COALESCE(p.exit_ip,p.endpoint) END)
                FROM proxy_pool p WHERE habilitado=1
                AND NOT EXISTS(
                SELECT 1 FROM proxy_reservas r WHERE r.endpoint=p.endpoint
                OR r.identidad=CASE WHEN p.lab_shared_exit=1 THEN 'lab:'||p.endpoint ELSE COALESCE(p.exit_ip,p.endpoint) END)''').fetchone()[0]

    def confirmar_salida(self,device_id,run_id,ip):
        ip=str(ipaddress.ip_address(ip))
        with self.database.conexion() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('''SELECT p.exit_ip,p.lab_shared_exit FROM proxy_reservas r JOIN proxy_pool p
                ON r.endpoint=p.endpoint WHERE r.id_adb=? AND r.run_id=? AND r.estado='activo' ''',
                (device_id,run_id)).fetchone()
            if row is None:
                raise ValueError('Reserva no disponible para verificar salida IP')
            if row['exit_ip'] and row['exit_ip']!=ip:
                raise ValueError('La IP de salida no coincide con proxy_pool.json')
            if row['lab_shared_exit']:
                return  # Se comprob\xf3 la salida real; la exclusividad local corresponde al endpoint.
            try:
                con.execute('UPDATE proxy_reservas SET identidad=? WHERE id_adb=? AND run_id=?',
                            (ip,device_id,run_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Colisi\xf3n: la IP de salida ya est\xe1 reservada por otra placa') from exc

    def finalizar(self,device_id,run_id,*,cleanup_ok):
        with self.database.conexion() as con:
            if cleanup_ok:
                con.execute('DELETE FROM proxy_reservas WHERE id_adb=? AND run_id=?',(device_id,run_id))
            else:
                con.execute("UPDATE proxy_reservas SET estado='cuarentena' WHERE id_adb=? AND run_id=?",(device_id,run_id))

    def retener_smoke(self,device_id,run_id):
        with self.database.conexion() as con:
            con.execute("UPDATE proxy_reservas SET estado='retenido_smoke' WHERE id_adb=? AND run_id=?",(device_id,run_id))
