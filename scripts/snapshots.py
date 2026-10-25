"""CLI de snapshots; por defecto verifica/recupera solo archivos propios ausentes."""
import argparse
from granjita.inventory import FleetStore,scan_fleet
from granjita.snapshots import eligible,reconcile_snapshots


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--device-id')
    parser.add_argument('--all',action='store_true')
    args=parser.parse_args()
    if not args.device_id and not args.all:parser.error('Selecciona --device-id o --all explícitamente.')
    store=FleetStore()
    ports=[int(p) for p in store.setting('ports','5037,5038').split(',')]
    store.save_fleet(scan_fleet(ports))
    rows=eligible(store)
    if args.device_id:rows=[r for r in rows if r['id']==args.device_id]
    if not rows:parser.error('Sin placas elegibles; concilia primero en la aplicación.')
    results=reconcile_snapshots(store,rows,lambda n,text:print(f'{n}: {text}',flush=True),args.capture)
    if any(r['detail'].startswith('Error') or r['detail'].startswith('Parcial') for r in results):raise SystemExit(1)

if __name__=='__main__':main()
