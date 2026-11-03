import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from PIL import Image
from core.panda_api import PandaClient,PandaError
from core.ocr_agent import analizar_pantalla_tiktok_async
from main_panda import ejecutar_qa_panda


def inventory():
    return [{'sort':2,'onlySerial':'hardware02','serial':'192.0.2.2:5555','status':'online'},
            {'sort':4,'onlySerial':'hardware04','serial':'192.0.2.4:5555','status':'online'}]


class PandaQATests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_is_fresh_png_and_batch_is_one_central_order(self):
        requests=[]
        async def request(payload):
            requests.append(payload)
            if payload['action']=='list':return inventory()
            if payload['action']=='Screen':
                Image.new('RGB',(100,200)).save(Path(payload['data']['savePath'])/'vendor.png')
        with tempfile.TemporaryDirectory() as folder:
            client=PandaClient(screenshots=folder,request=request)
            await client.preparar(['02','04'])
            image=await client.capturar_pantalla_dispositivo_async('02')
            self.assertEqual(image.name,'snapshot_02.png')
            with Image.open(image) as saved:
                self.assertEqual(saved.size,(100,200))
            result=await client.ejecutar_swipe_masivo_async(['02','04'])
            self.assertEqual(result['accepted'],['02','04'])
            gestures=[r for r in requests if r['action']=='pointerEvent']
            self.assertEqual(len(gestures),1)
            self.assertEqual(gestures[0]['devices'],'192.0.2.2:5555,192.0.2.4:5555')
            self.assertEqual(gestures[0]['data'],{'type':'6'})

    async def test_changed_identity_and_offline_are_excluded(self):
        rows=inventory();commands=[]
        async def request(payload):
            commands.append(payload)
            return rows
        client=PandaClient(request=request)
        await client.preparar(['02','04'])
        rows[0]['onlySerial']='replacement'
        rows[1]['status']='offline'
        self.assertEqual(await client.ejecutar_swipe_masivo_async(['02','04']),{'accepted':[],'excluded':['02','04']})
        self.assertFalse(any(c['action']=='pointerEvent' for c in commands))
        with self.assertRaises(PandaError):await client.capturar_pantalla_dispositivo_async('02')

    async def test_vision_is_opt_in_and_private_qa_rows_do_not_store_image_or_text(self):
        report={'descripcion':'texto privado de prueba','tema':'cocina','resumen_visual':'pantalla de prueba',
                'spam_sospechoso':False,'texto_legible':True}
        create=AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps(report),refusal=None))]))
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'qa.db';image=Path(folder)/'screen.png'
            Image.new('RGB',(100,200)).save(image)
            self.assertEqual((await analizar_pantalla_tiktok_async(image,client=client,db_path=db))['estado'],'omitido')
            create.assert_not_awaited()
            result=await analizar_pantalla_tiktok_async(image,client=client,db_path=db,allow_upload=True)
            self.assertEqual(result['informe'],report)
            self.assertEqual(create.call_args.kwargs['model'],'gpt-4o')
            with closing(sqlite3.connect(db)) as con:
                rows=con.execute('SELECT * FROM eventos_ia_qa').fetchall()
                self.assertEqual(rows[-1][6],'gpt-4o')
                self.assertNotIn(report['descripcion'],json.dumps(rows))

    async def test_offline_worker_does_not_stop_batch_and_sqlite_precedes_swipe(self):
        client=SimpleNamespace(preparar=AsyncMock(return_value={}),
            capturar_pantalla_dispositivo_async=AsyncMock(side_effect=[Path('fake.png'),PandaError('offline')]))
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'audit.db'
            async def swipe(devices):
                with closing(sqlite3.connect(db)) as con:
                    self.assertEqual(con.execute('SELECT count(*) FROM auditorias_panda').fetchone()[0],2)
                self.assertEqual(devices,['02'])
                return {'accepted':devices,'excluded':[]}
            client.ejecutar_swipe_masivo_async=AsyncMock(side_effect=swipe)
            with patch('main_panda.regular_retencion_de_carga',new=AsyncMock(return_value={'estado_retencion':'completado'})), \
                 patch('main_panda.analizar_pantalla_tiktok_async',new=AsyncMock(return_value={'estado':'omitido','informe':None,'latencia_ms':None})):
                await ejecutar_qa_panda(client,['02','04'],cycles=1,db_path=db)
            with closing(sqlite3.connect(db)) as con:
                rows=con.execute('SELECT id_placa,estado_operativo,swipe_estado FROM auditorias_panda ORDER BY id_placa').fetchall()
            self.assertEqual(rows,[('02','omitido','orden_aceptada'),('04','fallido','no_enviado')])

    async def test_failed_commit_prevents_swipe(self):
        client=SimpleNamespace(preparar=AsyncMock(return_value={}),
            capturar_pantalla_dispositivo_async=AsyncMock(side_effect=PandaError('offline')),
            ejecutar_swipe_masivo_async=AsyncMock())
        with patch('main_panda.regular_retencion_de_carga',new=AsyncMock(return_value={'estado_retencion':'completado'})), \
             patch('main_panda.guardar_lote_async',new=AsyncMock(side_effect=sqlite3.OperationalError)):
            with self.assertRaises(sqlite3.OperationalError):await ejecutar_qa_panda(client,['02'],cycles=1)
        client.ejecutar_swipe_masivo_async.assert_not_awaited()

    def test_rejects_external_or_credentialed_endpoint(self):
        for url in ['http://localhost:8080/api','ws://user:password@127.0.0.1:22222/','ws://example.org/']:
            with self.assertRaises(ValueError):PandaClient(url)

    async def test_live_panda_inventory_schema_may_omit_status(self):
        rows=inventory()
        for row in rows:row.pop('status')
        client=PandaClient(request=AsyncMock(return_value=rows))
        self.assertEqual(await client.preparar(['02','04']),{})
        rows[0]['status']='offline'
        with self.assertRaises(PandaError):client._bound(rows,'02')

    async def test_cancellation_is_persisted_and_never_swipes(self):
        entered=asyncio.Event()
        async def capture(device):
            entered.set()
            await asyncio.Future()
        client=SimpleNamespace(preparar=AsyncMock(return_value={}),
            capturar_pantalla_dispositivo_async=AsyncMock(side_effect=capture),
            ejecutar_swipe_masivo_async=AsyncMock())
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'audit.db'
            with patch('main_panda.regular_retencion_de_carga',new=AsyncMock(return_value={'estado_retencion':'completado'})):
                task=asyncio.create_task(ejecutar_qa_panda(client,['02'],cycles=1,db_path=db))
                await asyncio.wait_for(entered.wait(),3)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT estado_operativo FROM auditorias_panda').fetchone()[0],'cancelado')
        client.ejecutar_swipe_masivo_async.assert_not_awaited()

    async def test_atomic_batch_rolls_back_on_invalid_row(self):
        from core.panda_telemetry import guardar_lote_async
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'audit.db'
            await guardar_lote_async(db,'run',1,[])
            with self.assertRaises(KeyError):
                await guardar_lote_async(db,'run',1,[{'id_placa':'02','estado':'omitido'},{}])
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM auditorias_panda').fetchone()[0],0)

    async def test_adb_wrapper_uses_selected_panda_server_and_rejects_background_app(self):
        from core.adb_wrapper import AndroidDevice
        from core.adb_pool import DeviceRoute,ADBServer
        from config.proxies import ADBError
        device=AndroidDevice(DeviceRoute('exampleUSB',ADBServer('127.0.0.1',5038),'device'))
        with patch('core.adb_wrapper.verificar_adb',return_value='adb.exe'), \
             patch('core.adb_wrapper.subprocess.run',return_value=SimpleNamespace(stdout=b'OK')) as run:
            self.assertEqual(await device.ejecutar_comando(['get-state']),'OK')
            self.assertEqual(run.call_args.args[0][:7],['adb.exe','-H','127.0.0.1','-P','5038','-s','exampleUSB'])
        with patch.object(device,'ejecutar_comando',new=AsyncMock(return_value='mResumedActivity: another.app/.Main')):
            with self.assertRaises(ADBError):await device.verificar_app_visible()
