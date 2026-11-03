import copy
import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from core.diagnostics import (
    TEST_TEXT, analizar_gfxinfo, diagnosticar_dispositivo, generar_overlay,
    medir_rendimiento, probar_teclado,
)
from main import main


def components():
    node={'package':'app','bounds':'[20,30][80,90]'}
    return {'screen_size':[200,200],'text_components':[node],
            'candidates':{kind:[copy.deepcopy(node)] for kind in ('description','like','comments')}}


class OverlayTests(unittest.TestCase):
    def test_red_alpha_bounds_and_center(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            Image.new('RGB',(200,200),'white').save(root/'current.png')
            (root/'components.json').write_text(json.dumps(components()))
            result=generar_overlay(root/'current.png',root/'components.json',root/'debug.png')
            with Image.open(root/'debug.png') as output:
                r,g,b=output.getpixel((25,40))
                self.assertEqual(r,255)
                self.assertLess(g,255)
                self.assertEqual(output.getpixel((50,60)),(255,255,0))
            self.assertEqual(result['counts'],dict(description=1,like=1,comments=1))

    def test_rotation_mismatch_refuses_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            Image.new('RGB',(100,200)).save(root/'current.png')
            (root/'components.json').write_text(json.dumps(components()))
            with self.assertRaisesRegex(ValueError,'tamaño'):
                generar_overlay(root/'current.png',root/'components.json',root/'debug.png')

    def test_missing_candidates_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            data=components()
            data['candidates']['like']=[]
            Image.new('RGB',(200,200)).save(root/'current.png')
            (root/'components.json').write_text(json.dumps(data))
            result=generar_overlay(root/'current.png',root/'components.json',root/'debug.png')
            self.assertEqual(result['counts']['like'],0)
            self.assertTrue(result['warnings'])


class KeyboardTests(unittest.TestCase):
    @patch('core.diagnostics.teclado_unicode',return_value=nullcontext())
    @patch('core.diagnostics.inyectar_unicode')
    @patch('core.diagnostics.shell')
    @patch('core.diagnostics.capturar_pantalla_y_xml')
    def test_actual_xml_match_and_clear(self,capture,shell,inject,keyboard):
        shell.side_effect=lambda *args: 'Status: ok' if 'start' in args else 'original/.Ime'
        count=[0]
        def save(device_id, sessions):
            count[0]+=1
            text=TEST_TEXT if count[0]==2 else ''
            Path(sessions,'window_dump.xml').write_text(
                f'<hierarchy><node class="android.widget.EditText" focused="true" text="{text}"/></hierarchy>',
                encoding='utf-8')
        capture.side_effect=save
        with tempfile.TemporaryDirectory() as directory:
            result=probar_teclado('usb',directory,preguntar=Mock())
        self.assertTrue(result['exact_text_match'])
        inject.assert_called_once_with('usb',TEST_TEXT)
        self.assertTrue(any('ADB_CLEAR_TEXT' in call.args for call in shell.call_args_list))

    @patch('core.diagnostics.teclado_unicode',return_value=nullcontext())
    @patch('core.diagnostics.inyectar_unicode')
    @patch('core.diagnostics.shell',return_value='Status: ok')
    @patch('core.diagnostics.capturar_pantalla_y_xml')
    def test_no_focus_prevents_broadcast(self,capture,shell,inject,keyboard):
        def save(device_id,sessions):
            Path(sessions,'window_dump.xml').write_text('<hierarchy/>')
        capture.side_effect=save
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'EditText'):
                probar_teclado('usb',directory,preguntar=Mock())
        inject.assert_not_called()


class PerformanceTests(unittest.TestCase):
    def test_counter_parser_excludes_legacy(self):
        result=analizar_gfxinfo('Total frames rendered: 100\nJanky frames: 12 (12%)\nJanky frames (legacy): 80 (80%)')
        self.assertEqual(result['janky_frames'],12)
        self.assertFalse(analizar_gfxinfo('No process found')['available'])

    @patch('core.diagnostics.time.sleep')
    @patch('core.diagnostics.time.monotonic')
    @patch('core.diagnostics.shell')
    def test_interval_deltas_and_sustained_warning(self,shell,clock,sleep):
        # start, sample elapsed, remaining x5, final actual
        clock.side_effect=[0,0,0,3,3,6,6,9,9,12,12,12]
        shell.side_effect=[f'Total frames rendered: {100+i*20}\nJanky frames: {10+i*4}' for i in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            result=medir_rendimiento('usb','app',directory,seconds=12)
            self.assertTrue(Path(directory,'performance','summary.json').exists())
        self.assertTrue(result['sustained_jank_warning'])
        self.assertEqual(result['intervals'][0]['jank_percent'],20)
        self.assertEqual(result['status'],'warning')


class DiagnosticIntegrationTests(unittest.TestCase):
    @patch('main.verificar_adb')
    @patch('core.diagnostics.diagnosticar_dispositivo',return_value={'status':'passed'})
    @patch('core.ai_orchestrator.OpenAI',side_effect=AssertionError('No debe consultar OpenAI'))
    @patch('sys.argv',['main.py','--test-device','--diagnose-device'])
    @patch.dict('os.environ',{'PANDA_ENV_FILE':os.devnull},clear=True)
    def test_exact_cli_needs_no_key_or_proxy(self,openai,diagnose,adb):
        self.assertEqual(main(),0)
        diagnose.assert_called_once_with(package='com.zhiliaoapp.musically')
        openai.assert_not_called()

    @patch('core.diagnostics.verificar_adb')
    @patch('core.diagnostics.primer_dispositivo_usb',return_value='usb')
    @patch('core.diagnostics.shell',return_value=':0')
    @patch('core.diagnostics.capturar_pantalla_y_xml',return_value=components())
    @patch('core.diagnostics.capturar_png')
    @patch('core.diagnostics.generar_overlay',return_value={
        'counts':dict(description=1,like=1,comments=1),'warnings':[]})
    @patch('core.diagnostics.abrir_imagen')
    @patch('core.diagnostics.probar_teclado',return_value={'status':'passed','exact_text_match':True})
    @patch('core.diagnostics.medir_rendimiento',return_value={'status':'measured'})
    @patch('core.ai_orchestrator.OpenAI',side_effect=AssertionError('No debe consultar OpenAI'))
    def test_full_protocol_persists_narrow_certificate(self,openai,perf,keyboard,viewer,overlay,png,capture,shell,usb,adb):
        with tempfile.TemporaryDirectory() as directory:
            result=diagnosticar_dispositivo(package='app',directory=directory,
                preguntar=Mock(side_effect=['','s','']))
            stored=json.loads(Path(directory,'diagnostics.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(stored['openai_requests'],0)
        self.assertFalse(stored['network_modified'])
        openai.assert_not_called()
