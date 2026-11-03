"""QA masivo de solo lectura basado en inventario CSV verificado."""
import argparse
import asyncio
from contextlib import AsyncExitStack
import csv
import logging
import math
import os
from pathlib import Path
import re
import signal
import threading
import time
import unicodedata
from uuid import uuid4

from openai import AsyncOpenAI
from config.proxies import ProxyManager
from config.farm_policy import (load_farm_policy, EXIT_OK, EXIT_CONFIG_ERROR,
    EXIT_FARM_ABORT_FAIL, EXIT_FARM_ABORT_WARN, EXIT_FARM_ABORT_PRECHECK, EXIT_MESSAGES)
from config.farm_preflight import load_synthetic_fixture, run_farm_preflight, decide, write_evidence, build_real_context
from core.browser import ROOT
from core.database import Database
from core.mass_orchestrator import bloquear_granja
from core.panda_api import PandaClient
from core.panda_inventory import obtener_inventario
from core.project_env import load_project_environment
from main_panda import ejecutar_qa_panda

CSV_INVENTARIO_PATH=ROOT/'runs/inventario-panda-1a880267aa964be3bc500387ff7aa6c0/inventario.csv'
DB_PATH=ROOT/'telemetria_panda.db'
MAX_CONCURRENCY=5
TIMEOUT_PREFLIGHT_PROXY_SEGUNDOS=90
log=logging.getLogger('qa.panda.masivo')


def cargar_placas_activas_desde_csv(path=CSV_INVENTARIO_PATH):
    """Acepta los nombres reales y los encabezados del ejemplo sin inferir seriales."""
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4*1024*1024:
        raise ValueError('Inventario ausente o demasiado grande')
    placas=[];numbers=set();serials=set()
    with path.open(encoding='utf-8-sig',newline='') as file:
        reader=csv.DictReader(file)
        fields={str(name).strip().casefold() for name in reader.fieldnames or []}
        if not ({'numero_panda'}<=fields and bool({'serial','serial_fisico'}&fields) and 'transporte' in fields):
            raise ValueError('Encabezados del inventario no compatibles')
        for raw in reader:
            row={str(key).strip().casefold():(value or '').strip() for key,value in raw.items() if key is not None}
            number=row.get('numero_panda','')
            serial=row.get('serial_fisico') or row.get('serial','')
            if not number and not serial:
                continue
            if row.get('estado') and row['estado']!='vinculado':
                continue
            if not number.isdigit() or not 1<int(number)<=999999:
                raise ValueError('Numero Panda invalido')
            number=str(int(number)).zfill(2)
            if not serial:
                raise ValueError('Serial ausente en placa '+number)
            transport=row.get('transporte','')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{3,100}',serial) or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{3,100}',transport):
                raise ValueError('Identidad o transporte invalido')
            if number in numbers or serial in serials:
                raise ValueError('Inventario ambiguo por numero o serial duplicado')
            alias=row.get('alias') or row.get('alias_agx') or row.get('nombre_panda') or ''
            placas.append({'panda_id':number,'serial':serial,'alias':alias[:200],'transporte':transport})
            numbers.add(number);serials.add(serial)
    if not placas:
        raise ValueError('No hay placas verificadas en el inventario')
    return placas


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
    except asyncio.TimeoutError:
        log.error('Proxy no verificable')
        return 4
    except Exception:
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
        if args.preflight_proxy:
            code=await ejecutar_preflight_proxy_solo(args)
            if code!=EXIT_OK:
                cancelled=code==130
                return code
        policy=load_farm_policy()
        if args.preflight_proxy:
            manager=ProxyManager.desde_panda()
            if not policy.country:
                policy=replace(policy,country=getattr(manager,'_panda_country','').upper())
            ctx=await build_real_context(policy,manager,run_id,True)
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
    if getattr(args,'preflight_farm',False):
        return await ejecutar_preflight_farm_solo(args)
    if args.preflight_proxy and not args.execute_read_only:
        return await ejecutar_preflight_proxy_solo(args)
    validar_parametros(args)
    gate=RateGate(args.rpm)
    placas=await asyncio.to_thread(cargar_placas_activas_desde_csv,args.inventory)
    if len(placas)!=args.expected_count:
        raise ValueError('Cantidad CSV distinta de la esperada')
    log.info('Inventario cargado Placas %s',len(placas))
    run_id='panda-masivo-'+uuid4().hex
    if args.preflight_proxy:
        await asyncio.to_thread(load_project_environment)
        await ProxyManager.verificar_preflight(run_id=run_id)
    # Revalidacion fisica de lectura antes de admitir el lote.
    _,live,_=await obtener_inventario(Database())
    verified={row['numero_panda']:row['serial_fisico'] for row in live if row['estado']=='vinculado'}
    eligible=[p for p in placas if verified.get(p['panda_id'])==p['serial']]
    log.info('Vinculos fisicos actuales %s Excluidas %s',len(eligible),len(placas)-len(eligible))
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
    try:
        with bloquear_granja(ROOT/'sessions/farm.lock'):
            async with AsyncExitStack() as stack:
                options={'modelo':args.vision_model,'before_request':gate.wait}
                if args.allow_vision_upload:
                    await asyncio.to_thread(load_project_environment)
                    if not os.getenv('OPENAI_API_KEY'):
                        raise ValueError('Clave OpenAI ausente')
                    options['client']=await stack.enter_async_context(AsyncOpenAI(timeout=25,max_retries=0))
                await ejecutar_qa_panda(client,devices,cycles=args.cycles,hold_seconds=args.hold_seconds,
                    concurrency=args.concurrency,allow_upload=args.allow_vision_upload,stop=stop,
                    db_path=args.db,run_id=run_id,device_metadata={p['panda_id']:p for p in eligible},
                    vision_options=options)
    finally:
        signal.signal(signal.SIGINT,old)
    log.info('Proceso QA finalizado Run %s',run_id)
    return 0


class ASCIIFormatter(logging.Formatter):
    def format(self,record):
        return unicodedata.normalize('NFKD',super().format(record)).encode('ascii','ignore').decode('ascii')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,default=CSV_INVENTARIO_PATH)
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
