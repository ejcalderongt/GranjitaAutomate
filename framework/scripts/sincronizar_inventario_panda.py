"""Inventario privado conciliado; --apply guarda vínculos tras respaldar SQLite."""
import argparse
import asyncio
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.database import Database
from core.panda_inventory import obtener_inventario,guardar_inventario


def backup(source,target):
    with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('Respaldo de inventario no válido')


async def main_async(args):
    db=Database(args.database)
    run_id='inventario-panda-'+uuid4().hex
    directory=ROOT/'runs'/run_id
    directory.mkdir(parents=True)
    snapshot,rows,summary=await obtener_inventario(db)
    summary['run_id']=run_id
    summary['aplicado']=False
    if args.apply:
        await asyncio.to_thread(backup,db.path,directory/'database-before.sqlite3')
        await asyncio.to_thread(guardar_inventario,db,snapshot,rows,run_id)
        summary['aplicado']=True
    (directory/'resultado.json').write_text(json.dumps({'resumen':summary,'dispositivos':rows},
        ensure_ascii=False,indent=2),encoding='utf-8')
    with (directory/'inventario.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['numero_panda','serial_fisico','nombre_panda','alias_agx',
            'transporte','adb_host','adb_port','estado'],extrasaction='ignore')
        writer.writeheader();writer.writerows(sorted(rows,key=lambda r:int(r['numero_panda']) if r['numero_panda'].isdigit() else 999999))
    print(json.dumps(summary,ensure_ascii=False))
    print('Inventario privado:',directory/'inventario.csv')
    return 0 if summary['vinculados']==summary['panda_observados'] else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--database',type=Path)
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))
