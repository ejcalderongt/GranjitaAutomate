"""QA Panda finito: capturas y visión opcional, sin likes ni comentarios."""
import argparse
import asyncio
import logging
from pathlib import Path
import signal
import threading
from uuid import uuid4

from core.browser import ROOT
from core.load_testing import regular_retencion_de_carga
from core.mass_orchestrator import bloquear_granja
from core.ocr_agent import analizar_pantalla_tiktok_async
from core.panda_api import PandaClient
from core.panda_telemetry import guardar_lote_async

DEVICES_TO_AUDIT=['02','04','05','06','09','10']  # Ejemplo; CLI exige selección explícita.
log=logging.getLogger('qa.panda')


async def ejecutar_qa_panda(client,devices,*,cycles=5,hold_seconds=8,concurrency=2,
        allow_upload=False,stop=None,db_path=ROOT/'telemetria_panda.db',run_id=None,
        device_metadata=None,vision_options=None):
    if not 1<=cycles<=100 or not 8<=hold_seconds<=22 or not 1<=concurrency<=8:
        raise ValueError('Límites QA inválidos')
    stop=stop or threading.Event()
    run_id=run_id or 'panda-'+uuid4().hex
    await client.preparar(devices)
    semaphore=asyncio.Semaphore(concurrency)
    async def persist(rows,cycle):
        for row in rows:
            meta=(device_metadata or {}).get(row['id_placa'],{})
            row.update(serial=meta.get('serial'),alias=meta.get('alias'))
        await guardar_lote_async(db_path,run_id,cycle,rows)
    async def inspect(device_id,cycle):
        try:
            path=await client.capturar_pantalla_dispositivo_async(device_id)
            async with semaphore:
                if stop.is_set():
                    return {'id_placa':device_id,'estado':'cancelado'}
                audit=await analizar_pantalla_tiktok_async(path,allow_upload=allow_upload,
                    run_id=run_id,account_id='panda_'+device_id,cycle_id=str(cycle),
                    db_path=Path(db_path).with_name('telemetry_qa.db'),**(vision_options or {}))
            return {'id_placa':device_id,'estado':audit['estado'],'informe':audit['informe'],
                    'latencia_ms':audit['latencia_ms']}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('Placa %s: %s',device_id,type(exc).__name__)
            return {'id_placa':device_id,'estado':'fallido','error_codigo':type(exc).__name__}
    for cycle in range(1,cycles+1):
        retention=await regular_retencion_de_carga({},hold_seconds,stop)
        if retention['estado_retencion']=='cancelado':
            break
        tasks={device:asyncio.create_task(inspect(device,cycle)) for device in devices}
        try:
            rows=await asyncio.gather(*tasks.values())
        except asyncio.CancelledError:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(),return_exceptions=True)
            rows=[task.result() if task.done() and not task.cancelled() and task.exception() is None
                else {'id_placa':device,'estado':'cancelado'} for device,task in tasks.items()]
            await persist(rows,cycle)
            raise
        await persist(rows,cycle)
        if stop.is_set():
            break
        selected=[row['id_placa'] for row in rows if row['estado'] in ('exito','omitido')]
        try:
            result=await client.ejecutar_swipe_masivo_async(selected) if selected else {'accepted':[],'excluded':[]}
            for row in rows:
                row['swipe_estado']='orden_aceptada' if row['id_placa'] in result['accepted'] else 'no_enviado'
                if row['id_placa'] in result['excluded']:
                    row['estado']='offline_o_identidad_cambiada'
        except asyncio.CancelledError:
            for row in rows:
                if row['id_placa'] in selected:
                    row['swipe_estado']='resultado_desconocido'
            await persist(rows,cycle)
            raise
        except Exception:
            for row in rows:
                if row['id_placa'] in selected:
                    row['swipe_estado']='resultado_desconocido'
            await persist(rows,cycle)
            raise  # No reintentar ciegamente una orden masiva sin confirmación.
        await persist(rows,cycle)
        log.info('Ciclo %s/%s persistido: %s placas',cycle,cycles,len(rows))
    return run_id


async def main_async(args):
    run_id='panda-'+uuid4().hex
    client=PandaClient(args.panda_url,screenshots=ROOT/'screenshots'/run_id)
    failures=await client.preparar(args.devices)
    log.info('Preflight: %s seleccionadas, %s sin vínculo disponible',len(args.devices),len(failures))
    if not args.execute_read_only:
        return 2 if failures else 0
    if not args.ready:
        raise ValueError('Revisa manualmente TikTok en las placas y vuelve a ejecutar con --ready')
    stop=threading.Event()
    loop=asyncio.get_running_loop()
    task=asyncio.current_task()
    def cancel(*unused):
        stop.set()
        if not task.cancelling():
            loop.call_soon_threadsafe(task.cancel)
    old=signal.signal(signal.SIGINT,cancel)
    try:
        with bloquear_granja(ROOT/'sessions/farm.lock'):
            await ejecutar_qa_panda(client,args.devices,cycles=args.cycles,hold_seconds=args.hold_seconds,
                concurrency=args.concurrency,allow_upload=args.allow_vision_upload,stop=stop,
                db_path=Path(args.db),run_id=run_id)
    finally:
        signal.signal(signal.SIGINT,old)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--devices',nargs='+',required=True,help='Números visuales explícitos; nunca all')
    parser.add_argument('--panda-url',default='ws://127.0.0.1:22222/')
    parser.add_argument('--cycles',type=int,default=5)
    parser.add_argument('--hold-seconds',type=float,default=8)
    parser.add_argument('--concurrency',type=int,default=2)
    parser.add_argument('--db',default=str(ROOT/'telemetria_panda.db'))
    parser.add_argument('--execute-read-only',action='store_true')
    parser.add_argument('--ready',action='store_true',help='Operador confirma las placas en el feed de prueba')
    parser.add_argument('--allow-vision-upload',action='store_true',help='Autoriza enviar capturas completas a OpenAI gpt-4o')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(name)s %(message)s')
    try:
        return asyncio.run(main_async(args))
    except (KeyboardInterrupt,asyncio.CancelledError):
        log.info('QA cancelado; recursos liberados')
        return 130
    except Exception as exc:
        log.error('QA detenido: %s',type(exc).__name__)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
