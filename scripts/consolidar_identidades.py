"""Consolidar duplicados verificados. Vista previa por defecto; --apply aplica."""
import argparse,json,sqlite3
from contextlib import closing
from granjita.core import DATA,now
from granjita.inventory import FleetStore,scan_fleet
from granjita.panda_api import list_devices
from granjita.identity_consolidation import plan_consolidations,apply_consolidations
from granjita.physical import ordered_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panda-number',type=int,action='append',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    jobs=DATA/'automation.sqlite3'
    if args.apply and jobs.exists():
        with closing(sqlite3.connect(jobs.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('Ejecutando','En cola','Programado')").fetchone()[0]:
                raise ValueError('Espera a que terminen las tareas antes de consolidar identidades.')
    store=FleetStore()
    report=scan_fleet([5037,5038]);panda=list_devices()
    with store.connect() as db:plans=plan_consolidations(db,report,panda,args.panda_number)
    print(json.dumps(dict(mode='apply' if args.apply else 'preview',consolidations=len(plans),screens=[p['panda_number'] for p in plans]),ensure_ascii=False))
    if not args.apply or not plans:return
    stamp=now().replace(':','').replace('-','')
    folder=DATA/'backups';folder.mkdir(parents=True,exist_ok=True)
    store.backup(folder/('antes-consolidar-identidades-'+stamp+'.sqlite3'))
    # Releer Android/Panda antes de aplicar; no confiar solo en la vista previa.
    report=scan_fleet([5037,5038]);panda=list_devices()
    with store.connect() as db:plans=plan_consolidations(db,report,panda,args.panda_number)
    path=DATA/('consolidacion-identidades-'+stamp+'.json')
    path.write_text(json.dumps(dict(at=now(),plans=plans,state='prepared'),ensure_ascii=False,indent=2),encoding='utf-8')
    apply_consolidations(store,plans)
    store.save_fleet(scan_fleet([5037,5038]))
    rows=ordered_rows(store.fleet_devices(),store.positions())
    result=dict(at=now(),online=len({r['hardware_serial'] for r in rows if r['status']=='Validado'}),eligible=sum(r['status']=='Validado' and r['identity_state']=='Serial leído' for r in rows),duplicate_rows=sum(r['identity_state']=='Serial repetido: revisar' for r in rows))
    with store.connect() as db:result['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
    path.write_text(json.dumps(dict(at=now(),plans=plans,state='committed',verification=result),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if result['duplicate_rows'] or result['integrity']!='ok':raise RuntimeError('Aplicado; revisar verificación y auditoría antes de repetir.')


if __name__=='__main__':main()
