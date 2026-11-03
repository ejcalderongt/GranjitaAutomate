import json
import random
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pydantic import ValidationError

from config.proxies import configurar_proxy_dispositivo, limpiar_proxy_dispositivo
from core.actions import ejecutar_swipe_vertical
from core.ai_agent import Decision, analizar_pantalla_y_decidir, extraer_contexto
from main import construir_plan, descubrir_dispositivos, worker


class AndroidTests(unittest.TestCase):
    @patch('main.Database')
    @patch('main.signal.signal')
    @patch('main.limpiar_proxy_dispositivo')
    @patch('main.configurar_proxy_dispositivo',side_effect=RuntimeError('partial write'))
    @patch('main.adb',return_value='device')
    @patch('main.AppiumService')
    def test_cleanup_after_partial_proxy_failure(self, service, adb, configure, clean, signal, database):
        stop = Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        item = construir_plan(['usb'],['host:80'],1)[0]
        args = SimpleNamespace(stagger=0,cycles=1,max_failures=1)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                worker(item,args,{},stop,None,None,None,directory)
            events = [json.loads(line)['event'] for line in
                      (Path(directory)/'device-00.jsonl').read_text().splitlines()]
            self.assertIn('fatal',events)
            self.assertIn('proxy_cleared',events)
        clean.assert_called_once_with('usb')
        service.return_value.stop.assert_called_once()

    def test_40_unique_ports(self):
        plan = construir_plan([f'usb-{i}' for i in range(40)],
                              [f'proxy{i}.test:8080' for i in range(40)],40)
        ports = [p[k] for p in plan for k in ('appium_port','system_port','mjpeg_port')]
        self.assertEqual(len(set(ports)),120)
        with self.assertRaises(ValueError):
            construir_plan(['one'],['host:80'],40)
        with self.assertRaises(ValueError):
            construir_plan(['a','b'],['host:80','host:80'],2)

    @patch('main.descubrir_pool')
    def test_discovery(self, pool):
        pool.return_value=SimpleNamespace(devices={
            'a':SimpleNamespace(status='device'),'b':SimpleNamespace(status='offline'),
            'c':SimpleNamespace(status='unauthorized')})
        self.assertEqual(descubrir_dispositivos(),['a'])

    @patch('config.proxies.adb')
    def test_proxy_and_cleanup(self, adb):
        adb.side_effect = ['', 'proxy.test:8080', '', ':0']
        configurar_proxy_dispositivo('usb','proxy.test',8080)
        limpiar_proxy_dispositivo('usb')
        self.assertEqual(adb.call_args_list[0].args,
            ('-s','usb','shell','settings','put','global','http_proxy','proxy.test:8080'))
        with self.assertRaises(ValueError):
            configurar_proxy_dispositivo('usb','host;reboot',80)

    def test_real_w3c_payload(self):
        driver = Mock()
        driver.get_window_size.return_value = {'width':1080,'height':1920}
        ejecutar_swipe_vertical(driver,rng=random.Random(42))
        payload = driver.execute.call_args_list[0].args[1]['actions'][0]
        self.assertEqual(payload['parameters']['pointerType'],'touch')
        actions = payload['actions']
        moves = [a for a in actions if a['type']=='pointerMove']
        self.assertEqual(actions[1]['type'],'pointerDown')
        self.assertEqual(actions[-1]['type'],'pointerUp')
        self.assertLess(moves[-1]['y'],moves[0]['y'])
        self.assertTrue(all(0<a['x']<1080 and 0<a['y']<1920 for a in moves))

    def test_json_validation_and_refusal(self):
        decision = {'dar_like':True,'comentar':True,'texto_comentario':'qué buen video'}
        message = SimpleNamespace(content=json.dumps(decision),refusal=None)
        create = Mock(return_value=SimpleNamespace(choices=[
            SimpleNamespace(finish_reason='stop',message=message)]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.assertEqual(analizar_pantalla_y_decidir(None,client=client,contexto='{}'),decision)
        self.assertEqual(create.call_args.kwargs['model'],'gpt-4o-mini')
        message.refusal = 'no'
        with self.assertRaises(ValueError):
            analizar_pantalla_y_decidir(None,client=client,contexto='{}')
        for text in ('MAYÚSCULA','uno dos tres cuatro cinco seis siete ocho nueve'):
            with self.assertRaises(ValidationError):
                Decision(dar_like=False,comentar=True,texto_comentario=text)

    def test_accessibility_filter(self):
        result = extraer_contexto('<hierarchy><node text="visible"/><node displayed="false" text="oculto"/></hierarchy>')
        self.assertIn('visible',result)
        self.assertNotIn('oculto',result)
        with self.assertRaises(ValueError):
            extraer_contexto('<hierarchy/>')


if __name__ == '__main__':
    unittest.main()
