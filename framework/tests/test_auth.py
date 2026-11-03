import os
import tempfile
import unittest
from contextlib import ExitStack,nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from config.proxies import ADBError,ProxyAllocator
from core.adb_pool import ADBServer,DeviceRoute,PoolSnapshot
from core.database import Database
from core.mass_orchestrator import farm_worker
from core.selectors import analizar_autenticacion


def node(text='',**attributes):
    attrs={'package':'app','bounds':'[0,0][100,100]','text':text,**attributes}
    return '<node '+' '.join(f'{key}="{value}"' for key,value in attrs.items())+'/>'


class AuthParserTests(unittest.TestCase):
    def test_login_and_signup_override_profile(self):
        for label in ('Iniciar sesión','Registrarse','Log in','Sign up','Iniciar sesión o registrarse'):
            with self.subTest(label=label):
                xml='<hierarchy>'+node('Perfil')+node(label,clickable='true')+'</hierarchy>'
                self.assertFalse(analizar_autenticacion(xml,'app')['authenticated'])

    def test_profile_labels_or_known_ids_are_compatible(self):
        for attrs in ({'text':'Perfil'},{'text':'Me'},{'resource-id':'app:id/tab_profile'}):
            self.assertTrue(analizar_autenticacion('<hierarchy>'+node(**attrs)+'</hierarchy>','app')['authenticated'])

    def test_absent_profile_is_pending_only_after_initial_load(self):
        xml='<hierarchy>'+node('Para Ti')+'</hierarchy>'
        self.assertFalse(analizar_autenticacion(xml,'app')['authenticated'])
        self.assertIsNone(analizar_autenticacion(xml,'app',strict_profile=False)['authenticated'])

    def test_login_in_post_text_or_hidden_control_not_mistaken_for_button(self):
        xml='<hierarchy>'+node('Perfil')+node('Iniciar sesión')+node('Registrarse',clickable='true',displayed='false')+'</hierarchy>'
        self.assertTrue(analizar_autenticacion(xml,'app')['authenticated'])

    def test_nested_login_button_is_detected(self):
        xml='<hierarchy><node package="app" clickable="true">'+node('Iniciar sesión')+'</node></hierarchy>'
        self.assertFalse(analizar_autenticacion(xml,'app')['authenticated'])

    def test_other_package_is_indeterminate_not_missing_account(self):
        with self.assertRaises(ADBError):
            analizar_autenticacion('<hierarchy>'+node('Perfil',package='system')+'</hierarchy>','app')


class AccountStateTests(unittest.TestCase):
    def test_pending_survives_cleanup_inventory_and_can_be_revalidated(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Database(Path(temp)/'db.sqlite')
            db.registrar_auth('a',False,'login visible')
            db.actualizar_dispositivo('a',estado='Espera')
            db.sincronizar_inventario({'a':'device'})
            server=ADBServer('127.0.0.1',5038)
            db.sincronizar_pool(PoolSnapshot({'a':DeviceRoute('a',server,'device',[server])},{},[server]))
            self.assertEqual(db.dispositivos()[0]['estado'],'Pendiente Cuenta')
            self.assertEqual(db.kpis()['sin_cuenta'],1)
            db.registrar_auth('a',True,'ui compatible')
            self.assertEqual(db.kpis()['sin_cuenta'],0)
            self.assertEqual(db.dispositivos()[0]['estado'],'Calentando')


class WorkerAuthTests(unittest.TestCase):
    def run_worker(self,*,ready=True,cleanup_error=None,authenticated=False):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            path=Path(temp)/'db.sqlite'
            db=Database(path)
            allocator=ProxyAllocator(db)
            allocator.sincronizar([dict(endpoint='192.0.2.1:8000',host='192.0.2.1',port=8000,enabled=True)])
            allocator.reservar('a','run')
            db.iniciar_ejecucion('run',['a'],smoke=True)
            events=[]
            def cleanup(*args):
                events.append('cleanup')
                self.assertEqual(allocator.disponibles(),0)
                return cleanup_error
            mocks={
                'signal.signal':Mock(), 'adb':Mock(side_effect=lambda *a,**kw: 'usb:1-1' if a[-1]=='get-devpath' else 'device'),
                'shell':Mock(side_effect=lambda *a,**kw:'192.0.2.1:8000' if 'http_proxy' in a else 'Status: ok'), 'configurar_proxy_dispositivo':Mock(),
                'trafico_restringido':Mock(return_value=nullcontext(Mock())),
                'consultar_ip':Mock(return_value='203.0.113.1'),
                'esperar_feed':Mock(return_value={'ready':ready}),
                'comprobar_cuenta':Mock(side_effect=lambda *a,**kw: events.append('auth') or
                    {'authenticated':authenticated,'reason':'ui compatible' if authenticated else 'login visible'}),
                'cleanup_worker':Mock(side_effect=cleanup),
                'OpenAI':Mock(side_effect=lambda **kwargs:events.append('client') or Mock()),
                'ejecutar_feed':Mock(side_effect=lambda *a,**kw:events.append('feed'))}
            for name,mock in mocks.items():stack.enter_context(patch('core.mass_orchestrator.'+name,mock))
            original_release=ProxyAllocator.finalizar
            def checked_release(instance,device_id,run_id,*,cleanup_ok):
                if not authenticated and cleanup_ok:
                    self.assertEqual(db.ips_ejecucion('run')[0]['confirmada'],0)
                return original_release(instance,device_id,run_id,cleanup_ok=cleanup_ok)
            stack.enter_context(patch.object(ProxyAllocator,'finalizar',new=checked_release))
            stop=Mock();stop.is_set.return_value=False
            args=SimpleNamespace(smoke_test=1,package='app',activity='.Main',cycles=1,rpm=30,max_failures=2)
            route=DeviceRoute('a',ADBServer('127.0.0.1',5038),'device')
            with self.assertRaises(SystemExit) as outcome:
                farm_worker({'route':route,'proxy':('192.0.2.1',8000),'directory':str(Path(temp)/'worker'),
                             'reservation_owner':'run'},args,stop,None,None,None,str(path))
            rows=db.dispositivos()
            if not authenticated:
                self.assertEqual(rows[0]['estado'],'Pendiente Cuenta')
                self.assertEqual(db.kpis()['sin_cuenta'],1)
                mocks['OpenAI'].assert_not_called()
                mocks['ejecutar_feed'].assert_not_called()
                stop.set.assert_not_called()
                if cleanup_error:
                    self.assertEqual(db.reservas_proxy()[0]['estado'],'cuarentena')
                    self.assertEqual(outcome.exception.code,1)
                else:
                    self.assertEqual(allocator.disponibles(),1)
                    self.assertEqual(outcome.exception.code,0)
                    self.assertEqual(db.ips_ejecucion('run')[0]['confirmada'],0)
                    allocator.reservar('clean','run')
                    allocator.confirmar_salida('clean','run','203.0.113.1')
                    db.registrar_ip('run','clean','203.0.113.1',smoke=True,confirmada=True)
            else:
                self.assertLess(events.index('auth'),events.index('client'))
                mocks['ejecutar_feed'].assert_called_once()
            return mocks['comprobar_cuenta'].call_args.kwargs

    def test_no_account_skips_api_and_releases_only_after_cleanup(self):
        self.run_worker()

    def test_login_blocks_feed_load_but_still_becomes_pending_account(self):
        self.assertFalse(self.run_worker(ready=False)['strict_profile'])

    def test_cleanup_failure_keeps_quarantined_proxy(self):
        self.run_worker(cleanup_error='USB desconectado')

    def test_successful_auth_precedes_client_creation(self):
        self.run_worker(authenticated=True)


class AuthDashboardTests(unittest.TestCase):
    def test_pending_account_metric_and_yellow_row(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_resource.clear()
        try:
            with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(temp)/'db.sqlite')}):
                db=Database();db.registrar_auth('a',False,'login visible')
                with patch('config.proxies.adb',return_value='List of devices attached\na device\n'),patch('core.adb_pool.socket.create_connection'):
                    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui/dashboard.py')).run(timeout=20)
                self.assertFalse(app.exception)
                metric=next(m for m in app.metric if m.label=='Placas sin Cuenta Activa')
                self.assertEqual(metric.value,'1')
                self.assertEqual(app.dataframe[0].value.iloc[0]['estado'],'🟡 Pendiente Cuenta')
        finally:st.cache_resource.clear()
