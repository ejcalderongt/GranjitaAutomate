"""Auditoría de apps/cuentas sin abrir ni navegar aplicaciones."""
import argparse,json,sqlite3
from contextlib import closing
from granjita.core import DATA
from granjita.inventory import FleetStore,scan_fleet
from granjita.physical import ordered_rows
from granjita.app_inventory import CATALOG
from granjita.app_inventory_ui import AppAuditWorker


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--all',action='store_true');selection.add_argument('--device-id',action='append')
    parser.add_argument('--screen',action='store_true',help='Leer pantalla visible, sin abrir la app.')
    parser.add_argument('--app',choices=list(CATALOG),default='tiktok')
    args=parser.parse_args()
    if args.screen and args.app!='tiktok':parser.error('El adaptador de cuentas automático inicial es TikTok. Las demás apps admiten inventario técnico y validación manual.')
    jobs=DATA/'automation.sqlite3'
    if jobs.exists():
        with closing(sqlite3.connect(jobs.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('Ejecutando','En cola','Programado')").fetchone()[0]:parser.error('Hay tareas activas. Espera a que termine el lote.')
    store=FleetStore();store.save_fleet(scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')]))
    rows=[r for r in ordered_rows(store.fleet_devices(),store.positions()) if r['status']=='Validado' and r['identity_state']=='Serial leído']
    if args.device_id:
        selected=set(args.device_id)
        if selected-{r['id'] for r in rows}:parser.error('Una ficha elegida no está validada inequívocamente.')
        rows=[r for r in rows if r['id'] in selected]
    if not rows:parser.error('No hay dispositivos aptos para consultar.')
    worker=AppAuditWorker(store,rows,'screen' if args.screen else 'technical',args.app)
    reports=[];worker.completed.connect(reports.append)
    worker.progress.connect(lambda n,total,name:print(f'Comprobados {n}/{total}',flush=True))
    worker.run()
    if not reports:raise RuntimeError('No se recibió resultado de auditoría.')
    print(json.dumps(reports[0],ensure_ascii=False))
    if reports[0]['errors']:raise SystemExit(1)


if __name__=='__main__':main()
