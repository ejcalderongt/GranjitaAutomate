import base64
import copy
import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from unittest.mock import Mock, patch

from pydantic import ValidationError
from config.proxies import ADBError
from core.ai_orchestrator import (
    ADB_IME, DecisionFeed, consultar_decision, ejecutar_acciones, ejecutar_feed,
    extraer_contexto_componentes, inyectar_unicode, objetivo_unico,
    teclado_unicode, capturar_reporte,
    comentar_video,
)


def setUpModule():
    global _database_temp,_database_env
    _database_temp=tempfile.TemporaryDirectory()
    _database_env=patch.dict(os.environ,{'TIKTOK_DB_PATH':str(Path(_database_temp.name)/'test.db')})
    _database_env.start()


def tearDownModule():
    _database_env.stop()
    _database_temp.cleanup()


def decision(**changes):
    data = dict(interactuar=False,dar_like=False,comentar=False,
                comentario_texto='',tiempo_retencion_segundos=12)
    data.update(changes)
    return data


def report(text='un video de prueba #qa'):
    desc = dict(text=text,package='app',resource_id='app:id/caption')
    like = dict(text='',content_desc='Me gusta',package='app',clickable=True,
                enabled=True,selected=False,checked=False,center_px=[900,500])
    return dict(udid='usb',screen_size=[1000,1000],
                candidates={'description':[desc],'like':[like],'comments':[]},
                clickable_components=[like],text_components=[desc,like])


def api_client(data):
    message = SimpleNamespace(content=json.dumps(data,ensure_ascii=False),refusal=None)
    choice = SimpleNamespace(finish_reason='stop',message=message)
    return Mock(chat=SimpleNamespace(completions=SimpleNamespace(
        create=Mock(return_value=SimpleNamespace(choices=[choice])))))


class AIContractTests(unittest.TestCase):
    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.capturar_reporte',return_value=report())
    @patch('core.ai_orchestrator.ejecutar_acciones')
    def test_tcp_transport_does_not_become_interaction_identity(self,execute,capture,sleep):
        from core.database import Database
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'db.sqlite')
            ejecutar_feed('127.0.0.1:5555',package='app',videos=1,directory=directory,
                database=db,database_device_id='physical-01',client=api_client(decision()))
            rows,_=db.interacciones()
            self.assertEqual(rows[0]['id_adb'],'physical-01')
            self.assertEqual(db.dispositivos()[0]['id_adb'],'physical-01')
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[0],'127.0.0.1:5555')

    def test_json_mode_model_and_local_random_duration(self):
        client = api_client(decision())
        result = consultar_decision({'text':'un video','source':'description'},client,rng=random.Random(42))
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call['response_format'],{'type':'json_object'})
        self.assertEqual(call['model'],'gpt-4o-mini')
        self.assertEqual(result.tiempo_retencion_segundos,random.Random(42).randint(12,28))
        self.assertIn('spam',call['messages'][0]['content'])

    def test_contract_rejects_inconsistent_types_and_text(self):
        cases = [decision(dar_like=True),decision(interactuar='true'),
                 decision(tiempo_retencion_segundos=True),decision(tiempo_retencion_segundos=29),
                 decision(interactuar=True,comentar=True,comentario_texto='MAYÚSCULA'),
                 decision(interactuar=True,comentar=True,comentario_texto='1 2 3 4 5 6 7 8 9'),
                 decision(extra='bad')]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ValidationError):
                DecisionFeed.model_validate(case)

    def test_empty_context_forces_no_actions(self):
        client = api_client(decision(interactuar=True,dar_like=True))
        self.assertFalse(consultar_decision({'text':'','source':'empty'},client).interactuar)

    def test_refusal_and_truncation_rejected(self):
        client = api_client(decision())
        choice = client.chat.completions.create.return_value.choices[0]
        choice.message.refusal = 'no'
        with self.assertRaises(ValueError):
            consultar_decision({'text':'video'},client)
        choice.message.refusal = None
        choice.finish_reason = 'length'
        with self.assertRaises(ValueError):
            consultar_decision({'text':'video'},client)

    def test_context_priority_and_fallback(self):
        data = report()
        self.assertEqual(extraer_contexto_componentes(data)['source'],'description')
        data['candidates']['description']=[]
        self.assertEqual(extraer_contexto_componentes(data)['source'],'hashtags')
        data['text_components']=[]
        data['clickable_components']=[{'text':'video muy bonito','center_relative':[.3,.7]}]
        self.assertEqual(extraer_contexto_componentes(data)['source'],'nearby_clickables')

    def test_ambiguous_or_selected_like_not_clicked(self):
        data = report()
        self.assertIsNotNone(objetivo_unico(data,'like','app'))
        data['candidates']['like'][0]['selected']=True
        self.assertIsNone(objetivo_unico(data,'like','app'))
        data['candidates']['like'][0]['selected']=False
        second = copy.deepcopy(data['candidates']['like'][0])
        second['center_px']=[700,500]
        data['candidates']['like'].append(second)
        self.assertIsNone(objetivo_unico(data,'like','app'))


class ActionTests(unittest.TestCase):
    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.teclado_unicode',return_value=nullcontext())
    @patch('core.ai_orchestrator.capturar_reporte')
    @patch('core.ai_orchestrator.shell')
    def test_comment_verified_unicode_then_send_and_close(self,shell,capture,keyboard,sleep):
        data=report()
        comments=dict(package='app',clickable=True,center_px=[900,700])
        data['candidates']['comments']=[comments]
        modal=report('')
        field=dict(package='app',text='Añade un comentario…',center_px=[300,900],clickable=True)
        modal['candidates']['comment_input']=[field]
        written=copy.deepcopy(modal)
        written['candidates']['comment_input'][0]['text']='qué alegría 🥳'
        written['candidates']['comment_send']=[dict(package='app',clickable=True,center_px=[900,900])]
        capture.side_effect=[modal,written,data]
        record=Mock()
        with tempfile.TemporaryDirectory() as directory:
            result=comentar_video('usb','qué alegría 🥳',data,'app',directory,Mock(),record)
        self.assertEqual(result,data)
        taps=[c.args[3:] for c in shell.call_args_list if c.args[1:3]==('input','tap')]
        self.assertEqual(taps,[('900','700'),('300','900'),('900','900')])
        records=[c.args[0] for c in record.call_args_list]
        self.assertEqual(records,['comment_send_attempt','comment_send_click'])

    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.teclado_unicode',return_value=nullcontext())
    @patch('core.ai_orchestrator.capturar_reporte')
    @patch('core.ai_orchestrator.shell')
    def test_mismatched_unicode_prevents_send(self,shell,capture,keyboard,sleep):
        data=report()
        data['candidates']['comments']=[dict(package='app',clickable=True,center_px=[900,700])]
        modal=report('')
        modal['candidates']['comment_input']=[dict(package='app',text='',center_px=[300,900])]
        modal['candidates']['comment_send']=[dict(package='app',clickable=True,center_px=[900,900])]
        capture.side_effect=[modal,modal]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ADBError,'Unicode'):
                comentar_video('usb','qué alegría',data,'app',directory,Mock(),Mock())
        self.assertFalse(any(c.args[1:]==('input','tap','900','900') for c in shell.call_args_list))

    @patch('core.ai_orchestrator.shell')
    def test_unicode_is_utf8_base64_not_shell_text(self,shell):
        text = 'qué alegría 🥳; $(hola)'
        inyectar_unicode('usb',text)
        args = shell.call_args.args
        self.assertIn('ADB_INPUT_B64',args)
        self.assertNotIn(text,args)
        self.assertEqual(base64.b64decode(args[-1]).decode('utf-8'),text)

    @patch('core.ai_orchestrator.shell')
    def test_ime_restored_even_on_failure(self,shell):
        state = {'ime':'original/.Ime'}
        def run(device,*args):
            if args[:2]==('ime','list'):
                return f'original/.Ime\n{ADB_IME}' if '-a' in args else 'original/.Ime'
            if args[:2]==('ime','set'):
                state['ime']=args[2]
            if args[:2]==('settings','get'):
                return state['ime']
            return ''
        shell.side_effect=run
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                with teclado_unicode('usb',directory):
                    self.assertEqual(state['ime'],ADB_IME)
                    raise RuntimeError('interrupted')
            self.assertFalse((Path(directory)/'ime_cleanup_required.txt').exists())
        self.assertEqual(state['ime'],'original/.Ime')
        self.assertTrue(any(call.args[1:]==('ime','disable',ADB_IME) for call in shell.call_args_list))

    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.capturar_reporte')
    @patch('core.ai_orchestrator.shell')
    def test_no_interaction_still_waits_and_swipes(self,shell,capture,sleep):
        data=report()
        capture.return_value=data
        check=Mock()
        ejecutar_acciones('usb',decision(),data,package='app',directory='unused',check=check,record=Mock())
        self.assertEqual(sleep.call_count,12)
        self.assertEqual(shell.call_count,1)
        args=shell.call_args.args
        self.assertEqual(args[1:3],('input','swipe'))
        values=list(map(int,args[3:7]))
        self.assertTrue(all(abs(v-base)<=15 for v,base in zip(values,[500,800,500,230])))

    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.capturar_reporte')
    @patch('core.ai_orchestrator.shell')
    def test_stale_context_skips_tap(self,shell,capture,sleep):
        capture.return_value=report('otro video')
        ejecutar_acciones('usb',decision(interactuar=True,dar_like=True),report(),
                         package='app',directory='unused',check=Mock(),record=Mock())
        self.assertFalse(any('tap' in c.args for c in shell.call_args_list))
        self.assertTrue(any('swipe' in c.args for c in shell.call_args_list))

    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.capturar_reporte')
    @patch('core.ai_orchestrator.shell')
    def test_usb_failure_stops_without_gestures(self,shell,capture,sleep):
        with self.assertRaises(ADBError):
            ejecutar_acciones('usb',decision(),report(),package='app',directory='unused',
                             check=Mock(side_effect=ADBError('USB offline')),record=Mock())
        shell.assert_not_called()

    @patch('core.ai_orchestrator.capturar_pantalla_y_xml')
    def test_report_loaded_from_file_and_bound_to_device(self,capture):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'components.json'
            path.write_text(json.dumps(report()),encoding='utf-8')
            self.assertEqual(capturar_reporte('usb',directory)['udid'],'usb')
            with self.assertRaises(ValueError):
                capturar_reporte('other-usb',directory)

    @patch('core.ai_orchestrator.time.sleep')
    @patch('core.ai_orchestrator.capturar_reporte',side_effect=lambda *args: report())
    @patch('core.ai_orchestrator.shell')
    def test_five_cycles_decision_audit_and_swipes(self,shell,capture,sleep):
        client=api_client(decision())
        with tempfile.TemporaryDirectory() as directory:
            ejecutar_feed('usb',package='app',videos=5,directory=directory,client=client)
            events=[json.loads(line) for line in (Path(directory)/'audit.jsonl').read_text().splitlines()]
        self.assertEqual(sum(e['event']=='decision' for e in events),5)
        self.assertEqual(sum(e['event']=='swipe' for e in events),5)
        self.assertEqual(events[-1]['event'],'complete')
        self.assertEqual(client.chat.completions.create.call_count,5)
        from core.database import Database
        db=Database()
        with db.conexion() as con:
            rows=con.execute('SELECT * FROM interacciones WHERE run_id=?',(events[-1]['run_id'],)).fetchall()
        self.assertEqual(len(rows),5)
        self.assertTrue(all(row['estado']=='completada' and row['ia_valida']==1 for row in rows))

    @patch('core.ai_orchestrator.capturar_reporte',return_value=report())
    @patch('core.ai_orchestrator.ejecutar_acciones',side_effect=ADBError('ambiguous tap'))
    def test_ambiguous_action_aborts_without_retry(self,execute,capture):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ADBError):
                ejecutar_feed('usb',package='app',videos=5,directory=directory,
                              client=api_client(decision(interactuar=True,dar_like=True)))
            events=[json.loads(line) for line in (Path(directory)/'audit.jsonl').read_text().splitlines()]
        self.assertEqual(execute.call_count,1)
        self.assertEqual(events[-1]['event'],'aborted')
