"""Comprobar el último lote de apertura sin volver a lanzar aplicaciones."""
import json
from granjita.core import DATA
from granjita.automation import JobStore
from granjita.inventory import FleetStore
from granjita.physical import ordered_rows
from granjita.task_results import present_task,batch_text
from granjita.automation_ui import VerificationWorker


def main():
    jobs=object.__new__(JobStore);jobs.path=DATA/'automation.sqlite3'
    with jobs.db() as db:
        if db.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('Ejecutando','En cola','Programado')").fetchone()[0]:
            raise ValueError('Hay tareas activas. Espera a que termine el lote.')
    batch=jobs.latest_batch_summary()
    if not batch or not batch['preparation'] or not batch['finished']:
        raise ValueError('No hay un lote de apertura terminado para verificar.')
    store=object.__new__(FleetStore);store.path=DATA/'granjita.sqlite3'
    rows={r['id']:r for r in ordered_rows(store.fleet_devices(),store.positions())}
    tasks=[]
    for saved in jobs.batch_tasks(batch['batch']):
        if saved['action']!='app_prepare':continue
        row=rows.get(saved['device_id']) or dict(id=saved['device_id'],status='Sin verificar',port=saved['port'],serial=saved['serial'],hardware_serial='')
        tasks.append(dict(saved,row=row,app_source=present_task(saved)['source']))
    VerificationWorker(jobs,tasks).run()
    result=jobs.latest_batch_summary()
    print(batch_text(result))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
