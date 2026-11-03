import asyncio
from contextlib import closing
import csv
import logging
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from main_panda_masivo import cargar_placas_activas_desde_csv,RateGate,ASCIIFormatter,validar_parametros


class PandaMassiveTests(unittest.IsolatedAsyncioTestCase):
    def write_csv(self,path,header,rows):
        with path.open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.writer(file);writer.writerow(header);writer.writerows(rows)

    def test_real_headers_bom_and_exclusions(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'inventory.csv'
            self.write_csv(path,['numero_panda','serial_fisico','alias_agx','transporte','estado'],[
                ['01','physical01','offline','192.0.2.1:5555','vinculado'],
                ['02','physical02','alias02','192.0.2.2:5555','vinculado'],
                ['03','','empty','192.0.2.3:5555','vinculado'],
                ['04','physical04','pending','192.0.2.4:5555','sin_adb_verificado']])
            rows=cargar_placas_activas_desde_csv(path)
            self.assertEqual(rows,[{'panda_id':'02','serial':'physical02','alias':'alias02','transporte':'192.0.2.2:5555'}])

    def test_example_headers_and_duplicate_hardware(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'inventory.csv'
            self.write_csv(path,['Numero_Panda','serial','alias','transporte'],[
                ['2','hardware','name','192.0.2.2:5555']])
            self.assertEqual(cargar_placas_activas_desde_csv(path)[0]['panda_id'],'02')
            with path.open('a',encoding='utf-8') as file:file.write('04,hardware,name,192.0.2.4:5555\n')
            with self.assertRaises(ValueError):cargar_placas_activas_desde_csv(path)

    async def test_rate_gate_spaces_request_starts(self):
        gate=RateGate(300);starts=[]
        async def begin():
            await gate.wait();starts.append(time.monotonic())
        await asyncio.gather(*(begin() for _ in range(3)))
        self.assertTrue(all(b-a>=.18 for a,b in zip(starts,starts[1:])))

    def test_parameters_reject_more_than_five_requests_and_logs_are_ascii(self):
        args=SimpleNamespace(concurrency=6,cycles=5,hold_seconds=8,expected_count=34)
        with self.assertRaises(ValueError):validar_parametros(args)
        text=ASCIIFormatter('%(message)s').format(logging.LogRecord('qa',20,'',1,'Prueba \u2713',(),None))
        self.assertTrue(text.isascii())

    async def test_metadata_and_legacy_table_survive_schema_extension(self):
        from core.panda_telemetry import guardar_lote_async
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'audit.db'
            with closing(sqlite3.connect(db)) as con:
                con.execute('''CREATE TABLE auditorias_panda (run_id TEXT,ciclo INTEGER,timestamp_utc TEXT,
                    id_placa TEXT,resultado_auditoria_visual TEXT,estado_operativo TEXT,latencia_ms REAL,
                    error_codigo TEXT,swipe_estado TEXT,PRIMARY KEY(run_id,ciclo,id_placa))''')
                con.execute("INSERT INTO auditorias_panda VALUES ('old',1,'old','04',NULL,'omitido',NULL,NULL,'no_enviado')")
                con.commit()
            await guardar_lote_async(db,'run',1,[{'id_placa':'02','serial':'physical02','alias':'Alias QA',
                'estado':'exito','informe':{'tema':'test'}}])
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM auditorias_panda').fetchone()[0],2)
                self.assertEqual(con.execute("SELECT serial,alias FROM logs_panda_farm WHERE run_id='run'").fetchone(),('physical02','Alias QA'))

    async def test_massive_worker_never_exceeds_five_vision_calls(self):
        from main_panda import ejecutar_qa_panda
        active=0;maximum=0
        async def vision(*args,**kwargs):
            nonlocal active,maximum
            active+=1;maximum=max(maximum,active)
            await asyncio.sleep(.02)
            active-=1
            return {'estado':'omitido','informe':None,'latencia_ms':None}
        client=SimpleNamespace(preparar=AsyncMock(return_value={}),
            capturar_pantalla_dispositivo_async=AsyncMock(return_value=Path('fake.png')),
            ejecutar_swipe_masivo_async=AsyncMock(return_value={'accepted':[],'excluded':[]}))
        with tempfile.TemporaryDirectory() as folder:
            with patch('main_panda.regular_retencion_de_carga',new=AsyncMock(return_value={'estado_retencion':'completado'})), \
                 patch('main_panda.analizar_pantalla_tiktok_async',new=AsyncMock(side_effect=vision)):
                await ejecutar_qa_panda(client,[str(i) for i in range(2,10)],cycles=1,
                    concurrency=5,db_path=Path(folder)/'db.sqlite')
        self.assertEqual(maximum,5)
