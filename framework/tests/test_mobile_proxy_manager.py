import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx

from config.proxies import ProxyManager, ProxyRotationError
from core.telemetry import inicializar_db_telemetria


CONFIG={'PROXY_HOST':'proxy.example','PROXY_PORT':'1080','PROXY_PROTOCOL':'socks5',
        'PROXY_USER':'test-user','PROXY_PASS':'proxy-secret',
        'PROXY_ROTATION_URL':'https://control.example/rotate?token=rotation-secret',
        'PROXY_ROTATION_WAIT_SECONDS':'0'}


class MobileProxyManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_residential_entrypoint_ignores_absent_rotation_url(self):
        with tempfile.TemporaryDirectory() as folder:
            config={key:value for key,value in CONFIG.items() if key!='PROXY_ROTATION_URL'}
            config.update(PROXY_MODE='rotating_residential',PROXY_PROVIDER='proxy_cheap')
            control_calls=[]
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:control_calls.append(r))) as control, \
                       httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ip':'8.8.8.8'}))) as proxy:
                manager=ProxyManager(settings=config,telemetry_db=Path(folder)/'qa.db',control_client=control,proxy_client=proxy)
                for entry in (manager.preparar_conexion,manager.ejecutar_ciclo_rotacion_segura,manager.rotar_ip_movil):
                    self.assertEqual(await entry(),'8.8.8.8')
                manager._validate_rotation_url()
            self.assertEqual(control_calls,[])
            with closing(sqlite3.connect(Path(folder)/'qa.db')) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_red_qa WHERE accion='rotacion'").fetchone()[0],0)

    async def test_residential_mode_needs_no_webhook_or_ip_change_and_allows_browser_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'qa.db'
            calls=[]
            def forbidden(request):
                calls.append(request)
                raise AssertionError('A residential preflight must not call a modem API')
            async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as c, \
                       httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ip':'8.8.8.8'}))) as p:
                manager=ProxyManager(settings={**CONFIG,'PROXY_MODE':'rotating_residential','PROXY_PROVIDER':'proxy_cheap',
                    'PROXY_ROTATION_URL':'','PROXY_ROTATION_WAIT_SECONDS':'30'},telemetry_db=path,control_client=c,proxy_client=p)
                for _ in range(2):
                    self.assertEqual(await asyncio.wait_for(manager.preparar_conexion(),1),'8.8.8.8')
                await manager.validar_ip_navegador('1.1.1.1')
            self.assertEqual(calls,[])
            with closing(sqlite3.connect(path)) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_red_qa WHERE accion='rotacion'").fetchone()[0],0)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_red_qa WHERE modo='rotating_residential' AND estado='verificado'").fetchone()[0],3)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_red_qa WHERE cambio_ip=1").fetchone()[0],0)

    async def test_proxycheap_residential_rejects_http_configuration(self):
        with self.assertRaises(ProxyRotationError) as error:
            ProxyManager(settings={**CONFIG,'PROXY_MODE':'rotating_residential','PROXY_PROVIDER':'proxy_cheap','PROXY_PROTOCOL':'http'})
        self.assertEqual(error.exception.code,'proxy_cheap_requires_socks5')

    async def test_residential_browser_still_requires_a_public_ip(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=ProxyManager(settings={**CONFIG,'PROXY_MODE':'rotating_residential'},telemetry_db=Path(folder)/'qa.db')
            with self.assertRaises(ProxyRotationError):
                await manager.validar_ip_navegador('192.168.1.1')

    async def test_request_cancellation_cancels_inflight_http_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            started=asyncio.Event();cancel=asyncio.Event();calls=[]
            async def control(request):
                calls.append(request);started.set()
                await asyncio.Future()
            async with httpx.AsyncClient(transport=httpx.MockTransport(control)) as c, \
                       httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ip':'8.8.8.8'}))) as p:
                manager=ProxyManager(settings=CONFIG,telemetry_db=Path(folder)/'qa.db',control_client=c,proxy_client=p)
                task=asyncio.create_task(manager.rotar_ip_movil(cancel))
                await asyncio.wait_for(started.wait(),5)
                cancel.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task,1)
            self.assertEqual(len(calls),1)

    async def test_browser_ip_must_match_verified_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            addresses=iter(('8.8.8.8','1.1.1.1'))
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200))) as c, \
                       httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ip':next(addresses)}))) as p:
                manager=ProxyManager(settings=CONFIG,telemetry_db=Path(folder)/'qa.db',control_client=c,proxy_client=p)
                await manager.rotar_ip_movil()
                with self.assertRaises(ProxyRotationError) as error:
                    await manager.validar_ip_navegador('8.8.8.8',latencia_ms=1)
                self.assertEqual(error.exception.code,'browser_ip_mismatch')
            with closing(sqlite3.connect(Path(folder)/'qa.db')) as con:
                self.assertEqual(con.execute("SELECT evento FROM eventos_red_qa WHERE fase='navegador'").fetchone()[0],'Fallo de Validación de Red')

    async def test_change_is_verified_and_last_session_is_compared_without_storing_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path=inicializar_db_telemetria(Path(folder)/'qa.db')
            addresses=iter(('8.8.8.8','1.1.1.1','1.1.1.1'))
            pulses=[]
            def control(request):
                pulses.append(request)
                return httpx.Response(200,json={'success':True})
            def proxy(request):
                self.assertEqual(request.url.host,'api.ipify.org')
                return httpx.Response(200,json={'ip':next(addresses)})
            async with httpx.AsyncClient(transport=httpx.MockTransport(control)) as control_client, \
                       httpx.AsyncClient(transport=httpx.MockTransport(proxy)) as proxy_client:
                manager=ProxyManager(settings=CONFIG,telemetry_db=path,control_client=control_client,proxy_client=proxy_client)
                self.assertEqual(await manager.ejecutar_ciclo_rotacion_segura(),'1.1.1.1')
                self.assertFalse(control_client.is_closed)
                self.assertFalse(proxy_client.is_closed)
                manager2=ProxyManager(settings=CONFIG,telemetry_db=path,control_client=control_client,proxy_client=proxy_client)
                with self.assertRaises(ProxyRotationError) as error:
                    await manager2.rotar_ip_movil()
                self.assertEqual(error.exception.code,'ip_unchanged')
            self.assertEqual(len(pulses),2)
            with closing(sqlite3.connect(path)) as con:
                con.row_factory=sqlite3.Row
                rows=[dict(row) for row in con.execute('SELECT * FROM eventos_red_qa')]
            stored=str(rows)
            for secret in ('test-user','proxy-secret','rotation-secret','8.8.8.8','1.1.1.1','control.example'):
                self.assertNotIn(secret,stored)
            self.assertTrue(any(row['error_codigo']=='ip_unchanged' for row in rows))
            self.assertTrue(any(row['evento']=='Fallo de Validación de Red' for row in rows))
            self.assertTrue(any(row['estado']=='verificado' and row['cambio_ip']==1 for row in rows))

    async def test_http_failure_never_confuses_acknowledgement_with_changed_ip(self):
        for payload,status,code in (({'success':False},200,'rotation_provider_rejected'),({},503,'rotation_http_503')):
            with tempfile.TemporaryDirectory() as folder:
                addresses=[]
                def proxy(request):
                    addresses.append(request)
                    return httpx.Response(200,json={'ip':'8.8.8.8'})
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(status,json=payload))) as c, \
                           httpx.AsyncClient(transport=httpx.MockTransport(proxy)) as p:
                    manager=ProxyManager(settings=CONFIG,telemetry_db=Path(folder)/'qa.db',control_client=c,proxy_client=p)
                    with self.assertRaises(ProxyRotationError) as error:
                        await manager.rotar_ip_movil()
                    self.assertEqual(error.exception.code,code)
                self.assertEqual(len(addresses),1)

    async def test_missing_rotation_link_stops_before_any_network_request(self):
        with tempfile.TemporaryDirectory() as folder:
            calls=[]
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:calls.append(r))) as client:
                manager=ProxyManager(settings={**CONFIG,'PROXY_ROTATION_URL':''},telemetry_db=Path(folder)/'qa.db',control_client=client,proxy_client=client)
                with self.assertRaises(ProxyRotationError) as error:
                    await manager.rotar_ip_movil()
            self.assertEqual(error.exception.code,'rotation_url_missing')
            self.assertEqual(calls,[])

    async def test_cancellation_during_settle_does_not_probe_or_retry_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            issued=asyncio.Event();cancel=threading.Event();probes=[]
            def control(request):
                issued.set()
                return httpx.Response(200,json={'success':True})
            def proxy(request):
                probes.append(request)
                return httpx.Response(200,json={'ip':'8.8.8.8'})
            async with httpx.AsyncClient(transport=httpx.MockTransport(control)) as c, \
                       httpx.AsyncClient(transport=httpx.MockTransport(proxy)) as p:
                manager=ProxyManager(settings={**CONFIG,'PROXY_ROTATION_WAIT_SECONDS':'30'},telemetry_db=Path(folder)/'qa.db',control_client=c,proxy_client=p)
                task=asyncio.create_task(manager.rotar_ip_movil(cancel))
                await asyncio.wait_for(issued.wait(),5)
                cancel.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task,1)
            self.assertEqual(len(probes),1)
            with closing(sqlite3.connect(Path(folder)/'qa.db')) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM eventos_red_qa WHERE accion='rotacion' AND estado='cancelado'").fetchone()[0],1)

    async def test_ip_validation_requires_proxy_transport_and_closes_owned_client(self):
        with tempfile.TemporaryDirectory() as folder:
            client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'ip':'8.8.8.8'})))
            manager=ProxyManager(settings=CONFIG,telemetry_db=Path(folder)/'qa.db')
            with patch('httpx.AsyncClient',return_value=client) as create:
                self.assertEqual(await manager.obtener_ip_publica(),'8.8.8.8')
            options=create.call_args.kwargs
            self.assertEqual(str(options['proxy'].url),'socks5://proxy.example:1080')
            self.assertEqual(options['proxy'].auth,('test-user','proxy-secret'))
            self.assertFalse(options['trust_env'])
            self.assertTrue(client.is_closed)

    async def test_proxy_timeout_is_controlled_and_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            def timeout(request):
                raise httpx.ConnectTimeout('url includes secret',request=request)
            async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
                manager=ProxyManager(settings=CONFIG,telemetry_db=Path(folder)/'qa.db',proxy_client=client)
                with self.assertRaises(ProxyRotationError) as error:
                    await manager.obtener_ip_publica()
            self.assertEqual(str(error.exception),'proxy_timeout')
            with closing(sqlite3.connect(Path(folder)/'qa.db')) as con:
                self.assertEqual(con.execute("SELECT error_codigo FROM eventos_red_qa WHERE estado='fallido'").fetchone()[0],'proxy_timeout')

    async def test_env_file_supports_new_names_and_does_not_mix_old_password(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('\n'.join(f'{k}={v}' for k,v in {**CONFIG,'PROXY_USERNAME':'old','PROXY_PASSWORD':'old-secret'}.items()))
            with patch.dict('os.environ',{},clear=True):
                manager=ProxyManager(env_path=path,telemetry_db=Path(folder)/'qa.db')
            self.assertEqual(manager.browser_proxy()['username'],'test-user')
            self.assertEqual(manager.browser_proxy()['password'],'proxy-secret')
