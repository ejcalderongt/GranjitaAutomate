"""Piloto explícito de una sola placa, exclusivamente en gt.granjita.lab."""
import argparse
from granjita.inventory import FleetStore,scan_fleet
from granjita.automation import JobStore, run_lab, automate_status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-eligible',action='store_true',help='Elegir la primera conexión validada sin conflicto de identidad')
    parser.add_argument('--device-id')
    parser.add_argument('--pilot-batch',type=int,choices=[2,3],help='Prueba secuencial en 2 o 3 placas, cubriendo los puertos disponibles')
    parser.add_argument('--comment',default='Gracias por completar la prueba del laboratorio.')
    args=parser.parse_args()
    if not args.first_eligible and not args.device_id and not args.pilot_batch:
        parser.error('Indica --device-id o --first-eligible para autorizar el piloto.')
    store=FleetStore()
    store.save_fleet(scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')]))
    rows=[r for r in store.fleet_devices() if r['status']=='Validado' and r['identity_state']=='Serial leído' and (not args.device_id or r['id']==args.device_id)]
    if not rows:
        raise SystemExit('No hay una placa elegible.')
    if args.pilot_batch:
        chosen=[]
        for port in sorted({r['port'] for r in rows}):
            chosen.append(next(r for r in rows if r['port']==port))
        chosen += [r for r in rows if r['id'] not in {c['id'] for c in chosen}]
        unique={}
        for row in chosen:
            unique.setdefault(row['id'],row)
        rows=list(unique.values())[:args.pilot_batch]
    else:
        rows=rows[:1]
    jobs=JobStore()
    tasks=jobs.create(rows,args.comment)
    for task in tasks:
        row=task['row']
        print('Piloto en una placa. Puerto ADB:',row['port'],flush=True)
        jobs.update(task['id'],'Ejecutando')
        try:
            result=run_lab(row,args.comment,task['id'])
            jobs.update(task['id'],'Completado',result)
            print(result,flush=True)
        except Exception as exc:
            jobs.update(task['id'],'Revisar resultado',str(exc))
            raise
        print('Automate:',automate_status(row),flush=True)


if __name__=='__main__':
    main()
