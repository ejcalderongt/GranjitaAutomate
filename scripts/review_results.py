"""Cruzar trazas y auditoría sin alterar tareas ni contactar dispositivos."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sqlite3
import statistics
from granjita.core import DATA,now
from granjita.diagnostics import read_events


def review(batch_id=None):
    events=read_events(limit=10000)
    times=defaultdict(list)
    for event in events:
        if event['phase']=='end' and event['duration_ms'] is not None:times[event['process']].append(event['duration_ms'])
    performance={name:dict(samples=len(values),median_ms=round(statistics.median(values),1),max_ms=round(max(values),1)) for name,values in times.items()}
    report=dict(at=now(),event_window=len(events),possibly_truncated=len(events)==10000,performance=performance,error_events=sum(e['status']=='error' for e in events))
    path=DATA/'automation.sqlite3'
    if not path.exists():return report
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        if not batch_id:
            row=db.execute("SELECT batch FROM tasks WHERE action='lab_like_flow' GROUP BY batch HAVING COUNT(*)>1 ORDER BY MAX(rowid) DESC LIMIT 1").fetchone()
            batch_id=row['batch'] if row else None
        if batch_id:
            tasks=[dict(r) for r in db.execute('SELECT id,status FROM tasks WHERE batch=?',(batch_id,))]
            started=set();verified={};requested=set()
            for event in db.execute('SELECT e.task_id,e.kind,e.data FROM like_events e JOIN tasks t ON t.id=e.task_id WHERE t.batch=? ORDER BY e.id',(batch_id,)):
                data=json.loads(event['data']);key=(event['task_id'],data.get('target','lab_like_01'))
                if event['kind']=='started':started.add(key)
                if event['kind']=='click_requested':requested.add(key)
                if event['kind']=='verified':verified[key]=data['outcome']
            planned=0
            for row in db.execute('SELECT c.context FROM like_context c JOIN tasks t ON t.id=c.task_id WHERE t.batch=?',(batch_id,)):
                parameters=json.loads(row['context']).get('parameters') or {}
                planned+=parameters.get('count',1)
            report['batch']=dict(id=batch_id,devices=len(tasks),states=dict(Counter(t['status'] for t in tasks)),planned=planned,started=len(started),verified=len(verified),outcomes=dict(Counter(verified.values())),unconfirmed=len(started-set(verified)),not_started=max(0,planned-len(started)),click_requested_without_verification=len(requested-set(verified)))
    finally:db.close()
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch-id');parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=review(args.batch_id)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(encoded,encoding='utf-8')
    print(encoded)

if __name__=='__main__':main()
