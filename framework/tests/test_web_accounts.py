import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.browser import validar_account_id, directorio_cuenta
from core.actions import guardar_evidencia_visual
from core.web_orchestrator import construir_plan_web, ejecutar_ciclo_web
from types import SimpleNamespace


class WebAccountsTests(unittest.TestCase):
    def test_browser_descriptor_and_proxy(self):
        from core.browser import iniciar_navegador_tiktok
        pw=Mock()
        pw.chromium.launch_persistent_context.return_value.pages=[]
        pw.devices={'Pixel 5':{'viewport':{'width':393,'height':851},'is_mobile':True,'default_browser_type':'chromium'}}
        with tempfile.TemporaryDirectory() as folder, patch('playwright.sync_api.sync_playwright') as start:
            start.return_value.start.return_value=pw
            iniciar_navegador_tiktok('cuenta_01',{'host':'127.0.0.1','port':8001},sessions_root=folder)
            kwargs=pw.chromium.launch_persistent_context.call_args.kwargs
            self.assertNotIn('default_browser_type',kwargs)
            self.assertEqual(kwargs['proxy'],{'server':'http://127.0.0.1:8001'})
            self.assertTrue(kwargs['is_mobile'])

    def test_worker_error_does_not_stop_other_account(self):
        from core.web_orchestrator import worker_web
        with tempfile.TemporaryDirectory() as folder, \
             patch('core.web_orchestrator.ROOT',Path(folder)), \
             patch('core.web_orchestrator.Database'), \
             patch('core.web_orchestrator.ProxyAllocator'), \
             patch('core.web_orchestrator.liberar_api'), \
             patch('core.web_orchestrator.signal.signal'), \
             patch('core.web_orchestrator.iniciar_navegador_tiktok') as launch:
            stop=Mock()
            stop.wait.return_value=True
            args=SimpleNamespace(web_headless=False,web_login_only=True)
            launch.side_effect=RuntimeError('local test')
            status=Path(folder)/'failed.json'
            worker_web({'id':'a','proxy':{}},args,{},'test',stop,status)
            self.assertTrue(json.loads(Path(str(status)+'.result').read_text())['failed'])
            stop.set.assert_not_called()
            page,context,pw=Mock(),Mock(),Mock()
            page.request.get.return_value.text.return_value='8.8.8.8'
            launch.side_effect=None
            launch.return_value=(pw,context,page)
            status=Path(folder)/'healthy.json'
            worker_web({'id':'b','proxy':{'endpoint':'127.0.0.1:8001'}},args,{},'test',stop,status)
            result=json.loads(Path(str(status)+'.result').read_text())
            self.assertEqual(result,{'clean':True,'failed':False})
            context.close.assert_called_once()
            pw.stop.assert_called_once()

    def pool(self):
        return [{'endpoint':f'192.168.1.2:{8000+i}', 'host':'192.168.1.2',
                 'port':8000+i, 'enabled':True, 'exit_ip':f'8.8.8.{i}'} for i in range(1,4)]

    def test_account_paths(self):
        for name in ('../a', 'CON', 'cuenta/a', '', 'cuenta.01', 'LPT1', 'local_proxy'):
            with self.assertRaises(ValueError):
                validar_account_id(name)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(directorio_cuenta(folder,'cuenta_01').parent,Path(folder).resolve())

    def test_exclusive_mapping(self):
        plan=construir_plan_web(['a','b','c'],self.pool())
        self.assertEqual(len({p['proxy']['endpoint'] for p in plan}),3)
        for accounts in (['a','A'], ['a','b','c','d'],
                         [{'id':'a','proxy':'192.168.1.2:8001'},{'id':'b','proxy':'192.168.1.2:8001'}]):
            with self.assertRaises(ValueError):
                construir_plan_web(accounts,self.pool())

    def test_shared_exit_only_laboratory(self):
        pool=self.pool()
        for p in pool:
            p['exit_ip']='8.8.8.8'
        with self.assertRaises(ValueError):
            construir_plan_web(['a','b','c'],pool)
        for p in pool:
            p['lab_shared_exit']=True
        self.assertEqual(len(construir_plan_web(['a','b','c'],pool)),3)

    def test_screenshot_success_and_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.browser.ROOT',Path(folder)):
            page=Mock()
            page.screenshot.side_effect=lambda **kw: Path(kw['path']).write_bytes(b'PNG')
            result=guardar_evidencia_visual(page,'cuenta_01','decision_ia')
            self.assertEqual(result.parent,Path(folder)/'logs'/'cuenta_01')
            self.assertTrue(result.name.endswith('_decision_ia.png'))
            page.screenshot.side_effect=TimeoutError()
            self.assertIsNone(guardar_evidencia_visual(page,'cuenta_01','swipe_down'))
            self.assertEqual(len(list(result.parent.iterdir())),1)

    def test_evidence_order_and_capture_failure_prevents_action(self):
        page=Mock()
        page.locator.return_value.is_visible.return_value=False
        element=Mock()
        element.inner_text.return_value='Texto del video'
        element.get_attribute.return_value='false'
        selectors={k:k for k in ('login','authenticated','active_video','like')}
        events=[]
        with patch('core.scraper.extraer_contexto_video',return_value={'autor':'autor','descripcion':'Texto del video','sonido_original':'sonido'}), \
             patch('core.web_orchestrator.elemento_unico',return_value=element), \
             patch('core.ai_agent.evaluar_con_openai',return_value={'dar_like':True,'compartir':False,'comentar':False,'comentario':''}), \
             patch('core.web_orchestrator.guardar_evidencia_visual',side_effect=lambda p,a,s:events.append(s) or Path('ok')), \
             patch('core.web_orchestrator.hacer_swipe_down_movil',side_effect=lambda p,a:events.append('gesture')):
            ejecutar_ciclo_web(page,'cuenta_01',selectors,Mock(),execute=True)
        self.assertEqual(events,['post_decision','post_like','gesture'])
        with patch('core.scraper.extraer_contexto_video',return_value={'autor':'autor','descripcion':'Texto del video','sonido_original':'sonido'}), \
             patch('core.web_orchestrator.elemento_unico',return_value=element), \
             patch('core.ai_agent.evaluar_con_openai',return_value={'dar_like':True,'compartir':False,'comentar':False,'comentario':''}), \
             patch('core.web_orchestrator.guardar_evidencia_visual',return_value=None), \
             patch('core.web_orchestrator.hacer_swipe_down_movil'):
            element.click.reset_mock()
            ejecutar_ciclo_web(page,'cuenta_01',selectors,Mock(),execute=True)
            element.click.assert_not_called()
