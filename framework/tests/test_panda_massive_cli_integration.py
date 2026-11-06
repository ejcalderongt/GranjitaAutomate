import asyncio
from contextlib import closing, contextmanager, ExitStack, nullcontext
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import main_panda_masivo as m
import config.farm_preflight as farm_module
from core.adb_pool import ADBServer, DeviceRoute, PoolSnapshot
from config.farm_policy import FarmPolicy
from config.farm_preflight import ConstraintVerdict, migrate


@contextmanager
def combined_rig(root):
    """An entirely local combined CLI fixture; every identity is runtime-generated."""
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    serials=[uuid4().hex for _ in range(3)]
    mapping={'plates':[{'plate':'p'+str(index+1).zfill(2),'server':'localhost:5037',
        'device_serial_plain':serial,'device_ref':hashlib.sha256(serial.encode('ascii')).hexdigest()[:16]}
        for index,serial in enumerate(serials)]}
    inventory=root/'inventory.csv'
    with (Path(__file__).parent/'fixtures/csv/lab_stage3.csv').open(encoding='ascii',newline='') as stream:
        transports=[row['transporte'] for row in csv.DictReader(stream)]
    with inventory.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['numero_panda','device_ref','transporte','estado'])
        writer.writerows([[str(index+2),row['device_ref'],transports[index],'vinculado']
                          for index,row in enumerate(mapping['plates'])])
    args=SimpleNamespace(preflight_farm=True,preflight_proxy=True,execute_read_only=True,
        inventory=inventory,inventory_explicit=True,expected_count=3,cycles=1,concurrency=1,
        hold_seconds=12,rpm=30,ready=True,allow_vision_upload=False,vision_model='gpt-4o-mini',
        panda_url='synthetic',db=root/'telemetria_panda.db')
    for path,sql in ((args.db,'''CREATE TABLE auditorias_panda(
            run_id TEXT,ciclo INTEGER,id_placa TEXT,estado_operativo TEXT,
            PRIMARY KEY(run_id,ciclo,id_placa))'''),
                    (root/'telemetry_qa.db', '''CREATE TABLE eventos_ia_qa(
            id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,estado TEXT)''')):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(sql)
    ids=[str(index+2).zfill(2) for index in range(3)]
    state=SimpleNamespace(args=args,mapping=mapping,events=[],cancel=False,error=None,
        verdicts=[ConstraintVerdict(name,'PASS',name+' DATOS_ACREDITADOS | alternativa: revisar configuracion',{})
                  for name in ('C1','C2','C3','C4','C5')],
        ctx={'devices':ids,'synthetic':False,'real_connectors_ready':True,'excluded_devices':set()})
    async def proxy(_):
        state.events.append('proxy')
        return 0
    async def context(policy,manager,run_id,verified,selected_plates=None):
        state.events.append('context')
        state.selected=selected_plates
        return state.ctx
    async def farm(devices,policy,ctx,db):
        state.events.append('farm')
        migrate(db)
        with db:
            db.execute('INSERT INTO farm_preflight_runs VALUES (?,?,?,?,?,?,?)',
                       (ctx['run_id'],ctx['run_id'],policy.stage,'started','finished','proceed',0))
            for item in state.verdicts:
                db.execute('INSERT INTO farm_preflight_verdicts(run_id,"constraint",status) VALUES (?,?,?)',
                           (ctx['run_id'],item.constraint,item.status))
        return state.verdicts
    async def native(client,devices,**kwargs):
        state.events.append('native')
        state.native_kwargs=kwargs
        if state.error is not None:
            raise state.error
        if state.cancel:
            kwargs['stop'].set()
            return kwargs['run_id']
        with closing(sqlite3.connect(args.db)) as db, db:
            db.executemany('INSERT INTO auditorias_panda VALUES (?,?,?,?)',
                           [(kwargs['run_id'],1,device,'omitido') for device in devices])
        with closing(sqlite3.connect(root/'telemetry_qa.db')) as db, db:
            db.executemany('INSERT INTO eventos_ia_qa(run_id,estado) VALUES (?,?)',
                           [(kwargs['run_id'],'omitido') for _ in devices])
        return kwargs['run_id']
    client=Mock(preparar=AsyncMock(return_value={}))
    state.client=client
    live=[{'numero_panda':number,'serial_fisico':serial,'estado':'vinculado'} for number,serial in zip(ids,serials)]
    with ExitStack() as stack:
        for name,value in (('ROOT',root),('load_project_environment',Mock()),
                           ('load_latest_map',Mock(return_value=mapping)),
                           ('load_farm_policy',Mock(return_value=FarmPolicy(country='ES'))),
                           ('ejecutar_preflight_proxy_solo',AsyncMock(side_effect=proxy)),
                           ('build_real_context',AsyncMock(side_effect=context)),
                           ('run_farm_preflight',AsyncMock(side_effect=farm)),
                           ('Database',Mock()),('obtener_inventario',AsyncMock(return_value=(None,live,None))),
                           ('PandaClient',Mock(return_value=client)),('bloquear_granja',Mock(return_value=nullcontext())),
                           ('ejecutar_qa_panda',AsyncMock(side_effect=native))):
            state.__dict__[name]=stack.enter_context(patch.object(m,name,value))
        stack.enter_context(patch.object(m.ProxyManager,'desde_panda',return_value=SimpleNamespace(_panda_country='ES')))
        stack.enter_context(patch.object(m.ProxyManager,'verificar_preflight',new=AsyncMock(side_effect=AssertionError('Second proxy validation'))))
        state.signal=stack.enter_context(patch.object(m.signal,'signal',return_value=None))
        yield state


class PandaMassiveCLIIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)

    async def test_cli_combined_flags_run_preflight_before_native(self):
        with combined_rig(self.root) as rig:
            self.assertEqual(await m.main_async(rig.args),0)
            self.assertEqual(rig.events,['proxy','context','farm','native'])
            self.assertEqual([row['panda_id'] for row in rig.selected],['02','03','04'])
            with closing(sqlite3.connect(rig.args.db)) as db:
                self.assertEqual(db.execute('SELECT captcha_count,softblock_count,logout_count FROM farm_stage_metrics').fetchall(),[(None,None,None)])

    async def test_cli_combined_aborts_when_preflight_fails(self):
        with combined_rig(self.root) as rig:
            rig.verdicts[0]=ConstraintVerdict('C1','FAIL','C1 DATOS_NO_CUMPLEN | alternativa: revisar configuracion',{})
            self.assertEqual(await m.main_async(rig.args),2)
            rig.ejecutar_qa_panda.assert_not_awaited()
            rig.PandaClient.assert_not_called()

    async def test_cli_combined_excludes_failed_plates(self):
        with combined_rig(self.root) as rig:
            rig.ctx['excluded_devices'].add('03')
            self.assertEqual(await m.main_async(rig.args),4)
            rig.ejecutar_qa_panda.assert_not_awaited()

    async def test_cli_combined_requires_inventory(self):
        with combined_rig(self.root) as rig:
            rig.args.inventory_explicit=False
            rig.args.inventory=m.CSV_INVENTARIO_PATH
            self.assertEqual(await m.main_async(rig.args),1)
            self.assertEqual(rig.events,[])
            rig.load_latest_map.assert_not_called()
            report=json.loads(next((self.root/'runs').glob('farm_preflight_*.json')).read_text(encoding='ascii'))
            self.assertEqual(report['exit_code'],1)
        namespace=SimpleNamespace(inventory_explicit=False)
        action=m.ExplicitInventory(option_strings=['--inventory'],dest='inventory')
        action(None,namespace,m.CSV_INVENTARIO_PATH)
        self.assertTrue(namespace.inventory_explicit)

    async def test_cli_flags_alone_preserved(self):
        args=SimpleNamespace(preflight_farm=True,preflight_proxy=False,execute_read_only=False)
        with patch.object(m,'ejecutar_preflight_farm_solo',new=AsyncMock(return_value=0)) as farm, \
                patch.object(m,'ejecutar_flujo_nativo',new=AsyncMock()) as native:
            self.assertEqual(await m.main_async(args),0)
            farm.assert_awaited_once_with(args)
            native.assert_not_awaited()
        args=SimpleNamespace(preflight_farm=False,preflight_proxy=False,execute_read_only=True)
        with patch.object(m,'ejecutar_flujo_nativo',new=AsyncMock(return_value=0)) as native:
            self.assertEqual(await m.main_async(args),0)
            native.assert_awaited_once_with(args)

    async def test_cli_no_second_proxy_validation_in_combined_mode(self):
        with combined_rig(self.root) as rig:
            self.assertEqual(await m.main_async(rig.args),0)
            rig.ejecutar_preflight_proxy_solo.assert_awaited_once()
            self.assertEqual(rig.events.count('proxy'),1)

    async def test_cli_no_automatic_plate_substitution(self):
        with combined_rig(self.root) as rig:
            rig.ctx['devices']=['02','03','99']
            self.assertEqual(await m.main_async(rig.args),1)
            rig.ejecutar_qa_panda.assert_not_awaited()
        with combined_rig(self.root/'missing') as rig:
            rig.mapping['plates'].pop()
            self.assertEqual(await m.main_async(rig.args),1)
            rig.build_real_context.assert_not_awaited()
        with combined_rig(self.root/'duplicate') as rig:
            rig.ctx['devices']=['02','03','04','04']
            self.assertEqual(await m.main_async(rig.args),1)
            rig.ejecutar_qa_panda.assert_not_awaited()
        with combined_rig(self.root/'swapped') as rig:
            with rig.args.inventory.open(encoding='utf-8-sig',newline='') as stream:
                rows=list(csv.reader(stream))
            rows[1][1],rows[2][1]=rows[2][1],rows[1][1]
            with rig.args.inventory.open('w',encoding='utf-8-sig',newline='') as stream:
                csv.writer(stream).writerows(rows)
            self.assertEqual(await m.main_async(rig.args),1)
            rig.build_real_context.assert_not_awaited()
        with combined_rig(self.root/'routes') as rig:
            selected=m.canonical_selection(rig.args)
            properties={row['transporte']:'\n'.join('[%s]: [%s]' % pair for pair in (
                ('ro.serialno',row['serial']),('persist.sys.locale','es-ES'),
                ('persist.sys.timezone','Europe/Madrid'))) for row in selected}
            def read(*parts,**kwargs):
                self.assertEqual(parts[:4],('-H','localhost','-P','5037'))
                return properties[parts[parts.index('-s')+1]]
            with patch('core.adb_pool.descubrir_pool') as discover, \
                    patch('config.proxies.adb',side_effect=read) as adb:
                ctx=await farm_module.build_real_context(FarmPolicy(country='ES'),None,'fixture',False,
                                                         selected_plates=selected)
                self.assertEqual(ctx['devices'],['02','03','04'])
                self.assertEqual([call.args[5] for call in adb.call_args_list],
                                 [row['transporte'] for row in selected])
                properties.pop(selected[-1]['transporte'])
                rig.build_real_context.side_effect=farm_module.build_real_context
                self.assertEqual(await m.main_async(rig.args),m.EXIT_CONFIG_ERROR)
                rig.ejecutar_qa_panda.assert_not_awaited()
                discover.assert_not_called()

    async def test_cli_cancellation_130_preserves_resources(self):
        for index,exception in enumerate((None,asyncio.CancelledError())):
            with combined_rig(self.root/str(index)) as rig:
                rig.cancel=exception is None
                rig.error=exception
                self.assertEqual(await m.main_async(rig.args),130)
                self.assertEqual(rig.signal.call_count,2)
                report=json.loads(next((rig.args.inventory.parent/'runs').glob('farm_preflight_*.json')).read_text(encoding='ascii'))
                self.assertTrue(report['cancelled'])
                self.assertEqual(report['verdicts'],[])
                with closing(sqlite3.connect(rig.args.db)) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM farm_stage_metrics').fetchone()[0],0)
