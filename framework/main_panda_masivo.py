"""QA masivo de solo lectura basado en inventario CSV verificado."""
import argparse
import asyncio
from contextlib import AsyncExitStack
import csv
import json
import logging
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import threading
import time
import unicodedata
from uuid import uuid4

from openai import AsyncOpenAI
from config.proxies import ProxyManager
from config.farm_policy import (load_farm_policy, EXIT_OK, EXIT_CONFIG_ERROR,
    EXIT_FARM_ABORT_FAIL, EXIT_FARM_ABORT_WARN, EXIT_FARM_ABORT_PRECHECK, EXIT_MESSAGES)
from config.farm_preflight import (load_synthetic_fixture, run_farm_preflight, decide,
    write_evidence, build_real_context, record_native_metrics)
from core.browser import ROOT
from core.database import Database
from core.device_map import load_latest_map
from core.mass_orchestrator import bloquear_granja
from core.panda_api import PandaClient
from core.panda_inventory import obtener_inventario
from core.project_env import load_project_environment
from main_panda import ejecutar_qa_panda
from scripts.evidence_invariants import snapshot, compare, declare_run_writes

CSV_INVENTARIO_PATH=ROOT/'runs/inventario-panda-1a880267aa964be3bc500387ff7aa6c0/inventario.csv'
DB_PATH=ROOT/'telemetria_panda.db'
MAX_CONCURRENCY=5
TIMEOUT_PREFLIGHT_PROXY_SEGUNDOS=90
log=logging.getLogger('qa.panda.masivo')


def cargar_placas_activas_desde_csv(path=CSV_INVENTARIO_PATH, mapped=None):
    """Acepta los nombres reales y los encabezados del ejemplo sin inferir seriales."""
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4*1024*1024:
        raise ValueError('Inventario ausente o demasiado grande')
    placas=[];numbers=set();serials=set();references=set()
    with path.open(encoding='utf-8-sig',newline='') as file:
        reader=csv.DictReader(file)
        fields={str(name).strip().casefold() for name in reader.fieldnames or []}
        if not ({'numero_panda'}<=fields and bool({'serial','serial_fisico'}&fields or mapped is not None and 'device_ref' in fields) and 'transporte' in fields):
            raise ValueError('Encabezados del inventario no compatibles')
        for raw in reader:
            row={str(key).strip().casefold():(value or '').strip() for key,value in raw.items() if key is not None}
            number=row.get('numero_panda','')
            serial=row.get('serial_fisico') or row.get('serial','')
            reference=row.get('device_ref','')
            if not number and not serial and not reference:
                continue
            if row.get('estado') and row['estado']!='vinculado':
                continue
            if not number.isdigit() or not 1<int(number)<=999999:
                raise ValueError('Numero Panda invalido')
            number=str(int(number)).zfill(2)
            entry=None
            if 'device_ref' in fields or mapped is not None:
                if not re.fullmatch('[0-9a-f]{16}',reference) or reference in references:
                    raise ValueError('Referencia de dispositivo invalida')
                references.add(reference)
            if mapped is not None:
                entry=mapped.get(reference)
                if entry is None or serial and serial!=entry['device_serial_plain']:
                    raise ValueError('Referencia de dispositivo invalida')
                serial=entry['device_serial_plain']
            if not serial:
                raise ValueError('Serial ausente en placa '+number)
            transport=row.get('transporte','')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{3,100}',serial) or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{3,100}',transport):
                raise ValueError('Identidad o transporte invalido')
            if number in numbers or serial in serials:
                raise ValueError('Inventario ambiguo por numero o serial duplicado')
            alias=row.get('alias') or row.get('alias_agx') or row.get('nombre_panda') or ''
            plate={'panda_id':number,'serial':serial,'alias':alias[:200],'transporte':transport}
            if reference:
                plate['device_ref']=reference
            if entry is not None:
                plate.update(map_plate=entry['plate'],server=entry['server'])
            placas.append(plate)
            numbers.add(number);serials.add(serial)
    if not placas:
        raise ValueError('No hay placas verificadas en el inventario')
    return placas


def canonical_selection(args):
    load_project_environment()
    mapping=load_latest_map(ROOT)
    if not isinstance(mapping,dict) or not isinstance(mapping.get('plates'),list):
        raise ValueError('Mapeo de dispositivos no disponible')
    mapped={}
    serials=set();names=set()
    for item in mapping['plates']:
        if (not isinstance(item,dict) or not re.fullmatch('[0-9a-f]{16}',item.get('device_ref',''))
                or item['device_ref'] in mapped or item.get('device_serial_plain') in serials
                or item.get('plate') in names):
            raise ValueError('Mapeo de dispositivos inconsistente')
        mapped[item['device_ref']]=item
        serials.add(item.get('device_serial_plain'));names.add(item.get('plate'))
    plates=cargar_placas_activas_desde_csv(args.inventory,mapped=mapped)
    if (len(plates)!=args.expected_count or [item['map_plate'] for item in plates]
            != ['p'+str(index).zfill(2) for index in range(1,args.expected_count+1)]):
        raise ValueError('Seleccion de placas incompleta')
    return plates


def expected_native_writes(expected_count,cycles):
    count=expected_count*cycles
    return {name:{table:{'INSERT':count,'UPDATE':0,'DELETE':0}} for name,table in
            (('telemetria_panda.db','auditorias_panda'),('telemetry_qa.db','eventos_ia_qa'))}


async def ejecutar_preflight_y_lote(args):
    run_id='panda-masivo-'+uuid4().hex
    policy=None;ctx={'synthetic':False};verdicts=[];cancelled=False
    code=EXIT_FARM_ABORT_PRECHECK
    try:
        validar_parametros(args)
        if not getattr(args,'inventory_explicit',False):
            log.error('Inventario explicito requerido para corrida combinada')
            code=EXIT_CONFIG_ERROR
            return code
        plates=await asyncio.to_thread(canonical_selection,args)
        policy=load_farm_policy()
        if len(plates)!=policy.stage:
            raise ValueError('Seleccion de placas incompleta')
        if args.preflight_proxy:
            code=await ejecutar_preflight_proxy_solo(args)
            if code!=EXIT_OK:
                cancelled=code==130
                return code
        manager=ProxyManager.desde_panda() if args.preflight_proxy else None
        ctx=await build_real_context(policy,manager,run_id,args.preflight_proxy,selected_plates=plates)
        if (len(ctx.get('devices',[]))!=len(plates) or len(set(ctx['devices']))!=len(plates)
                or set(ctx['devices'])!={item['panda_id'] for item in plates}):
            raise ValueError('Seleccion de placas incompleta')
        ctx={**ctx,'run_id':run_id,'synthetic':False}
        db=sqlite3.connect(args.db,timeout=5)
        try:
            verdicts=await run_farm_preflight(ctx['devices'],policy,ctx,db)
        finally:
            db.close()
        for item in verdicts:
            if item.status in ('FAIL','WARN'):
                log.warning('%s',item.reason)
        if decide(verdicts,policy)=='abort':
            code=EXIT_FARM_ABORT_FAIL if policy.abort_on_fail and any(v.status=='FAIL' for v in verdicts) else EXIT_FARM_ABORT_WARN
            return code
        excluded=set(ctx.get('excluded_devices',()))|set(ctx.get('not_aligned',()))
        if any(item.status=='FAIL' for item in verdicts) and not excluded:
            excluded.update(ctx['devices'])
        plates=[item for item in plates if item['panda_id'] not in excluded]
        if len(plates)!=args.expected_count:
            code=EXIT_FARM_ABORT_PRECHECK
            return code
        code=await ejecutar_flujo_nativo(args,placas=plates,run_id=run_id,combined_policy=policy)
        if code==130:
            cancelled=True;verdicts=[]
        return code
    except (KeyboardInterrupt,asyncio.CancelledError):
        cancelled=True;verdicts=[];code=130
        return code
    except ValueError:
        code=EXIT_CONFIG_ERROR
        return code
    except Exception:
        code=EXIT_FARM_ABORT_PRECHECK
        return code
    finally:
        write_evidence(ROOT,run_id,policy,verdicts,code,cancelled=cancelled,ctx=ctx)


class RateGate:
    """Limita inicios por minuto; la concurrencia no es un limite de tokens."""
    def __init__(self,rpm):
        if not math.isfinite(rpm) or not 1<=rpm<=300:
            raise ValueError('RPM fuera de rango')
        self.interval=60/rpm
        self.next_start=0.0
        self.lock=asyncio.Lock()

    async def wait(self):
        async with self.lock:
            delay=self.next_start-time.monotonic()
            if delay>0:
                await asyncio.sleep(delay)
            self.next_start=time.monotonic()+self.interval


def validar_parametros(args):
    if not 1<=args.concurrency<=MAX_CONCURRENCY or not 1<=args.cycles<=100:
        raise ValueError('Concurrencia o ciclos fuera de rango')
    if not math.isfinite(args.hold_seconds) or not 8<=args.hold_seconds<=22:
        raise ValueError('Retencion fuera de rango')
    if not 1<=args.expected_count<=100:
        raise ValueError('Cantidad esperada invalida')


async def ejecutar_preflight_proxy_solo(args) -> int:
    MENSAJES_PROXY = {
        'Proxy no configurado': ('Proxy no configurado', 1),
        'Proxy invalido': ('Proxy invalido', 1),
    }
    try:
        await asyncio.to_thread(load_project_environment)
        await asyncio.wait_for(
            ProxyManager.verificar_preflight(run_id='proxy-'+uuid4().hex),
            timeout=TIMEOUT_PREFLIGHT_PROXY_SEGUNDOS,
        )
    except ValueError as exc:
        mensaje, codigo = MENSAJES_PROXY.get(str(exc), ('Proxy invalido', 1))
        log.error(mensaje)
        return codigo
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info('Preflight de proxy cancelado')
        return 130
    except Exception as exc:
        # Arbitrary exception messages can include proxy URLs or authentication.
        message = str(exc)
        safe_message = message if message in (*MENSAJES_PROXY, 'Proxy no verificable') else '[detalle reservado]'
        log.error('Proxy preflight fallo: %s: %s', type(exc).__name__, safe_message)
        log.error('Proxy no verificable')
        return 4
    log.info('Proxy verificado')
    return 0


async def ejecutar_preflight_farm_solo(args) -> int:
    import sqlite3
    from dataclasses import replace
    run_id='farm-'+uuid4().hex
    policy=None
    ctx={'synthetic': not args.preflight_proxy}
    verdicts=[]
    cancelled=False
    code=EXIT_FARM_ABORT_PRECHECK
    try:
        validar_parametros(args)
        if any(getattr(args,name,False) for name in ('execute_read_only','ready','allow_vision_upload')):
            raise ValueError('Politica de granja invalida')
        plates=None
        if getattr(args,'inventory_explicit',False):
            try:
                plates=await asyncio.to_thread(canonical_selection,args)
                policy=load_farm_policy()
                if len(plates)!=policy.stage:
                    raise ValueError('Seleccion de placas incompleta')
            except (OSError,ValueError):
                log.error('Inventario incompatible con el mapa DPAPI o la etapa configurada')
                code=EXIT_CONFIG_ERROR
                return code
        if args.preflight_proxy:
            code=await ejecutar_preflight_proxy_solo(args)
            if code!=EXIT_OK:
                cancelled=code==130
                return code
        if policy is None:
            policy=load_farm_policy()
        if args.preflight_proxy or plates is not None:
            manager=ProxyManager.desde_panda() if args.preflight_proxy else None
            if manager is not None and not policy.country:
                policy=replace(policy,country=getattr(manager,'_panda_country','').upper())
            try:
                ctx=await build_real_context(policy,manager,run_id,args.preflight_proxy,selected_plates=plates)
            except ValueError:
                if plates is not None:
                    log.error('Las rutas del inventario no coinciden con las identidades del mapa DPAPI')
                raise
        else:
            ctx=load_synthetic_fixture(ROOT/'tests/fixtures/farm_stage3.json')
        ctx={**ctx,'run_id':run_id}
        db=sqlite3.connect(args.db,timeout=5)
        try:
            verdicts=await run_farm_preflight(ctx['devices'],policy,ctx,db)
        finally:
            db.close()
        decision=decide(verdicts,policy)
        code=EXIT_OK
        if decision=='abort':
            code=EXIT_FARM_ABORT_FAIL if policy.abort_on_fail and any(v.status=='FAIL' for v in verdicts) else EXIT_FARM_ABORT_WARN
        for item in verdicts:
            if item.status in ('WARN','FAIL'):
                log.warning('%s',item.reason)
        return code
    except ValueError:
        code=EXIT_CONFIG_ERROR
        return code
    except (KeyboardInterrupt,asyncio.CancelledError):
        cancelled=True
        verdicts=[]
        code=130
        return code
    except Exception:
        code=EXIT_FARM_ABORT_PRECHECK
        return code
    finally:
        write_evidence(ROOT,run_id,policy,verdicts,code,cancelled=cancelled,ctx=ctx)


async def main_async(args):
    if getattr(args, 'stage', None) is not None:
        if any(getattr(args, name, False) for name in
               ('preflight_proxy', 'preflight_farm', 'execute_read_only', 'ready', 'allow_vision_upload')):
            return EXIT_CONFIG_ERROR
        from core.stage_scaling import stage_plan
        try:
            report = stage_plan(args.db, args.stage, getattr(args, 'stage_limits', None))
            path = ROOT / 'runs' / ('stage_plan_' + uuid4().hex + '.json')
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='ascii')
            return EXIT_OK if report['decision'] in ('promote', 'complete') else EXIT_FARM_ABORT_FAIL
        except (ValueError, OSError):
            return EXIT_CONFIG_ERROR
    if getattr(args, 'stage_limits', None) is not None:
        return EXIT_CONFIG_ERROR
    if getattr(args,'preflight_farm',False):
        if args.execute_read_only:
            return await ejecutar_preflight_y_lote(args)
        return await ejecutar_preflight_farm_solo(args)
    if args.preflight_proxy and not args.execute_read_only:
        return await ejecutar_preflight_proxy_solo(args)
    return await ejecutar_flujo_nativo(args)


async def ejecutar_flujo_nativo(args,*,placas=None,run_id=None,combined_policy=None):
    validar_parametros(args)
    gate=RateGate(args.rpm)
    if placas is None:
        placas=await asyncio.to_thread(cargar_placas_activas_desde_csv,args.inventory)
    if len(placas)!=args.expected_count:
        raise ValueError('Cantidad CSV distinta de la esperada')
    log.info('Inventario cargado Placas %s',len(placas))
    run_id=run_id or 'panda-masivo-'+uuid4().hex
    if args.preflight_proxy and combined_policy is None:
        await asyncio.to_thread(load_project_environment)
        await ProxyManager.verificar_preflight(run_id=run_id)
    # Revalidacion fisica de lectura antes de admitir el lote.
    _,live,_=await obtener_inventario(Database())
    verified={row['numero_panda']:row['serial_fisico'] for row in live if row['estado']=='vinculado'}
    eligible=[p for p in placas if verified.get(p['panda_id'])==p['serial']]
    log.info('Vinculos fisicos actuales %s Excluidas %s',len(eligible),len(placas)-len(eligible))
    if combined_policy is not None and len(eligible)!=args.expected_count:
        return EXIT_FARM_ABORT_PRECHECK
    if not eligible:
        raise ValueError('Ninguna placa coincide con inventario vivo')
    client=PandaClient(args.panda_url,screenshots=ROOT/'screenshots'/run_id,
        expected_identities={p['panda_id']:p['serial'] for p in eligible})
    devices=[p['panda_id'] for p in eligible]
    failures=await client.preparar(devices)
    devices=[d for d in devices if d not in failures]
    log.info('Preflight Placas admitidas %s',len(devices))
    if failures:
        log.warning('Preflight excluidas %s',sorted(failures))
    if len(devices)!=args.expected_count:
        if combined_policy is not None:
            return EXIT_FARM_ABORT_PRECHECK
        raise ValueError(
            'Placas admitidas '+str(len(devices))+
            ' distintas de las esperadas '+str(args.expected_count)+
            ' Fallidas '+str(len(failures))
        )
    if not args.execute_read_only:
        return 0 if len(devices)==len(placas) else 2
    if not args.ready:
        raise ValueError('Confirma admision manual con ready antes de ejecutar')
    if not devices:
        raise ValueError('No hay placas disponibles')
    stop=threading.Event()
    def cancel(*unused):
        log.info('SIGINT recibido Cancelacion cooperativa en curso')
        stop.set()
    old=signal.signal(signal.SIGINT,cancel)
    completed=False
    writes=expected_native_writes(args.expected_count,args.cycles) if combined_policy is not None else None
    paths={'telemetria_panda.db':Path(args.db),'telemetry_qa.db':Path(args.db).with_name('telemetry_qa.db')}
    before={};audits={}
    vision_observations=[]
    def record_observation(observation):
        vision_observations.append(observation)
        path=ROOT/'runs'/('vision_run_'+run_id+'.json')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'run_id':run_id,'rpm':args.rpm,
            'observations':vision_observations},ensure_ascii=True,indent=2),encoding='ascii')
        temporary.replace(path)
        log.info('Vision QA cuenta=%s resultado=%s json_valido=%s',observation['account_id'],
            observation['outcome'],str(observation['schema_valid']).lower())
    try:
        if writes is not None:
            before={name:snapshot(path) for name,path in paths.items()}
            if any(any('rows' not in before[name]['tables'].get(table,{}) for table in writes[name])
                   for name in paths):
                return EXIT_FARM_ABORT_PRECHECK
            writes={name:declare_run_writes(before[name],name,run_id,devices,args.cycles)
                    for name in paths}
        with bloquear_granja(ROOT/'sessions/farm.lock'):
            async with AsyncExitStack() as stack:
                options={'modelo':args.vision_model,'before_request':gate.wait}
                if args.allow_vision_upload:
                    await asyncio.to_thread(load_project_environment)
                    if not os.getenv('OPENAI_API_KEY'):
                        raise ValueError('Clave OpenAI ausente')
                    options['client']=await stack.enter_async_context(AsyncOpenAI(timeout=25,max_retries=0))
                    if combined_policy is not None:
                        options['on_observation']=record_observation
                await ejecutar_qa_panda(client,devices,cycles=args.cycles,hold_seconds=args.hold_seconds,
                    concurrency=args.concurrency,allow_upload=args.allow_vision_upload,stop=stop,
                    db_path=args.db,run_id=run_id,device_metadata={p['panda_id']:p for p in eligible},
                    vision_options=options)
                if combined_policy is not None:
                    if stop.is_set():
                        return 130
                    after={name:snapshot(path) for name,path in paths.items()}
                    audits={name:compare(before[name],after[name],run_id,mode='physical_run',
                        database=name,expected_writes=writes[name]) for name in paths}
                    if any(item['status']!='PASS' for item in audits.values()):
                        return EXIT_FARM_ABORT_PRECHECK
                    incident_counts=None
                    if args.allow_vision_upload:
                        expected={(f'panda_{device}',str(cycle)) for device in devices
                                  for cycle in range(1,args.cycles+1)}
                        actual={(row['account_id'],row['cycle_id']) for row in vision_observations}
                        if (actual!=expected or len(vision_observations)!=len(expected)
                                or any(row['outcome']!='success' or not row['schema_valid']
                                       or not row['api_called']
                                       or any(type(row[key]) is not int or row[key]<0
                                              for key in ('input_tokens','output_tokens'))
                                       for row in vision_observations)):
                            log.error('Evidencia de Vision incompleta')
                            return EXIT_FARM_ABORT_PRECHECK
                        incident_counts=tuple(sum(row['incidents'][key] is True for row in vision_observations)
                                              for key in ('captcha','softblock','logged_out'))
                    db=sqlite3.connect(args.db,timeout=5)
                    try:
                        if incident_counts is None:
                            record_native_metrics(db,run_id,combined_policy.stage,completed=True)
                        else:
                            record_native_metrics(db,run_id,combined_policy.stage,incident_counts=incident_counts)
                    finally:
                        db.close()
                    after={name:snapshot(path) for name,path in paths.items()}
                    audits={name:compare(before[name],after[name],run_id,mode='physical_run',
                        database=name,expected_writes=writes[name]) for name in paths}
                    if any(item['status']!='PASS' for item in audits.values()):
                        return EXIT_FARM_ABORT_PRECHECK
                    completed=True
    except (KeyboardInterrupt,asyncio.CancelledError):
        stop.set()
        raise
    finally:
        signal.signal(signal.SIGINT,old)
        if combined_policy is not None:
            if before and not completed:
                try:
                    audits={name:compare(before[name],snapshot(path),run_id,mode='physical_run',
                        database=name,expected_writes=writes[name]) for name,path in paths.items()}
                except Exception:
                    audits={'status':'FAIL','reason':'Evidencia de corrida no verificable'}
            report={'run_id':run_id,'completed':completed,'cancelled':stop.is_set(),
                    'expected_writes':writes,'database_audits':audits}
            path=ROOT/'runs'/('native_run_'+run_id+'.json')
            try:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='ascii')
            except Exception:
                log.error('Evidencia de corrida no verificable')
                if not stop.is_set():
                    raise RuntimeError('Evidencia de corrida no verificable') from None
    log.info('Proceso QA finalizado Run %s',run_id)
    return 0


class ASCIIFormatter(logging.Formatter):
    def format(self,record):
        return unicodedata.normalize('NFKD',super().format(record)).encode('ascii','ignore').decode('ascii')


class ExplicitInventory(argparse.Action):
    def __call__(self,parser,namespace,values,option_string=None):
        setattr(namespace,self.dest,values)
        namespace.inventory_explicit=True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=int, choices=[3, 10, 34], help='Planifica transicion sin ejecutar dispositivos')
    parser.add_argument('--stage-limits', type=Path, help='JSON local de min_samples por etapa')
    parser.set_defaults(inventory_explicit=False)
    parser.add_argument('--inventory',type=Path,default=CSV_INVENTARIO_PATH,action=ExplicitInventory)
    parser.add_argument('--db',type=Path,default=DB_PATH)
    parser.add_argument('--panda-url',default='ws://127.0.0.1:22222/')
    parser.add_argument('--expected-count',type=int,default=34)
    parser.add_argument('--cycles',type=int,default=5)
    parser.add_argument('--hold-seconds',type=float,default=8)
    parser.add_argument('--concurrency',type=int,default=5)
    parser.add_argument('--rpm',type=float,default=30)
    parser.add_argument('--vision-model',choices=['gpt-4o-mini','gpt-4o'],default='gpt-4o-mini')
    parser.add_argument('--execute-read-only',action='store_true',
        help='Ejecuta swipes esperas y Vision sin publicar comentar ni seguir')
    parser.add_argument('--preflight-proxy',action='store_true',
        help='Ejecuta preflight Patchright aislado antes de consultar Panda y exige PANDA_PROXY_*')
    parser.add_argument('--preflight-farm',action='store_true',default=False,
        help='Ejecuta C1 a C5 sinteticos; junto a preflight-proxy usa adaptadores reales de lectura')
    parser.add_argument('--ready',action='store_true')
    parser.add_argument('--allow-vision-upload',action='store_true')
    handler=logging.StreamHandler()
    handler.setFormatter(ASCIIFormatter('%(asctime)s %(name)s %(message)s'))
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    try:
        code=asyncio.run(main_async(parser.parse_args()))
    except (KeyboardInterrupt,asyncio.CancelledError):
        code=130
    except Exception as exc:
        message=str(exc)
        if isinstance(exc,ValueError) and (message in ('Proxy no configurado','Proxy invalido') or
                re.fullmatch(r'Serial ausente en placa [0-9]{1,6}',message) or
                re.fullmatch(r'Placas admitidas [0-9]+ distintas de las esperadas [0-9]+ Fallidas [0-9]+',message)):
            log.error('%s',message)
        else:
            log.error('Proceso detenido Tipo %s',type(exc).__name__)
        code=EXIT_CONFIG_ERROR
    if code==130:
        log.info('Proceso cancelado Recursos liberados')
        return 130
    if type(code) is not int or code not in EXIT_MESSAGES:
        log.error('Codigo de salida no reconocido')
        code=EXIT_CONFIG_ERROR
    if code!=EXIT_OK:
        log.error('%s',EXIT_MESSAGES[code])
    return code


if __name__=='__main__':
    raise SystemExit(main())
