"""Consultar/exportar trazas locales; no ejecuta acciones sobre dispositivos."""
import argparse
from collections import Counter
import json
from pathlib import Path
from granjita.diagnostics import read_events,feedback,stamp


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clear',action='store_true',help='Respaldar y limpiar trazas; conservar auditoría de tareas.')
    parser.add_argument('--run-id')
    parser.add_argument('--task-id')
    parser.add_argument('--export',type=Path)
    args=parser.parse_args()
    if args.clear:
        from granjita.diagnostics import clear_traces
        print(json.dumps(clear_traces(),ensure_ascii=False,indent=2))
        return
    rows=read_events(args.run_id,limit=10000,task_id=args.task_id)
    errors=[r for r in rows if r['status']=='error']
    slowest=sorted([r for r in rows if r['phase']=='end' and r['duration_ms'] is not None],key=lambda r:-r['duration_ms'])[:10]
    summary=dict(events=len(rows),runs=len({r['run_id'] for r in rows}),error_events=len(errors),categories=dict(Counter(r['metadata'].get('category','other') for r in errors)),slowest=[dict(process=r['process'],duration_ms=round(r['duration_ms'],1),run_id=r['run_id'],task_id=r['task_id']) for r in slowest])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if args.export:
        notes=[n for run in {r['run_id'] for r in rows} for n in feedback(run)]
        args.export.write_text(json.dumps(dict(schema_version=1,at=stamp(),possibly_truncated=len(rows)==10000,summary=summary,events=rows,feedback=notes),ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
