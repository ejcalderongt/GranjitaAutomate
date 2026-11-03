import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from core.browser import opciones_proxy,iniciar_navegador_tiktok
from ui.farm_control import WebJobs


class WebPanelTests(unittest.TestCase):
    def test_warmup_uses_video_description_and_enter(self):
        from core.web_orchestrator import ejecutar_ciclo_web
        page,active=Mock(),Mock()
        page.locator.return_value.is_visible.return_value=False
        active.get_attribute.return_value='video'
        active.locator.return_value.first.inner_text.return_value='descripción local'
        selectors={key:key for key in ('login','authenticated','active_video','comments','comment_input','comment_close')}
        with patch('core.web_orchestrator.elemento_unico',return_value=active), \
             patch('core.web_orchestrator.time') as clock, \
             patch('core.web_orchestrator.random.uniform',return_value=10), \
             patch('core.web_orchestrator.guardar_evidencia_visual',return_value=Path('evidence.png')), \
             patch('core.web_orchestrator.escribir_comentario_movil') as typing, \
             patch('core.web_orchestrator.hacer_swipe_feed_tiktok') as swipe, \
             patch('core.ai_agent.evaluar_con_openai',return_value={
                 'dar_like':False,'compartir':False,'comentar':True,'comentario':'qué buena prueba local'}) as ai:
            clock.monotonic.side_effect=[0,0,1,26]
            clock.perf_counter.side_effect=[0,0.1]
            self.assertTrue(ejecutar_ciclo_web(page,'cuenta_tiktok_01',selectors,Mock(),warmup=True,execute=True))
            self.assertEqual(ai.call_args.args[1]['descripcion'],'descripción local')
            typing.assert_called_once_with(page,active,'qué buena prueba local')
            page.keyboard.press.assert_called_once_with('Enter')
            swipe.assert_called_once_with(page,'cuenta_tiktok_01')

    def test_authenticated_proxy_is_normalized_without_credentials_in_server(self):
        result=opciones_proxy({'server':'http://user:p%40ss@127.0.0.1:8001'})
        self.assertEqual(result,{'server':'http://127.0.0.1:8001','username':'user','password':'p@ss'})

    def test_patchright_engine_and_persistent_profile(self):
        pw=Mock()
        pw.devices={'Pixel 5':{'default_browser_type':'chromium','is_mobile':True}}
        pw.chromium.launch_persistent_context.return_value.pages=[]
        with tempfile.TemporaryDirectory() as folder,patch('patchright.sync_api.sync_playwright') as start:
            start.return_value.start.return_value=pw
            iniciar_navegador_tiktok('cuenta_tiktok_01',{'host':'127.0.0.1','port':8001},
                engine='patchright',sessions_root=folder)
            self.assertEqual(Path(pw.chromium.launch_persistent_context.call_args.args[0]).name,'cuenta_tiktok_01')

    def test_panel_spawns_main_without_credentials_in_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'config').mkdir()
            (root/'config/proxy_pool.json').write_text(json.dumps({'mode':'laboratory','lab_host':'192.168.1.199',
                'proxies':[{'host':'192.168.1.199','port':8001,'enabled':True,'exit_ip':'8.8.8.8'}]}))
            job=WebJobs(root)
            with patch('ui.farm_control.subprocess.Popen') as spawn:
                job.start_web(endpoint='192.168.1.199:8001',profile='cuenta_tiktok_01',cycles=1,
                    login_only=True,execute=False,db_path=root/'test.db',username='test-user',password='test-password')
            args=spawn.call_args.args[0]
            self.assertIn('--web-login-only',args)
            self.assertIn('patchright',args)
            self.assertNotIn('test-password',' '.join(args))
            self.assertEqual(spawn.call_args.kwargs['env']['PANDA_WEB_PROXY_PASSWORD'],'test-password')
            self.assertEqual(json.loads((job.directory/'accounts.json').read_text())[0]['profile'],'cuenta_tiktok_01')
