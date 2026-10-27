"""Presentación de resultados sin reinterpretar ni modificar la auditoría."""
import json
from collections import Counter
from .app_sources import source_profile


def preparation_result(detail):
    if not isinstance(detail,str):return {}
    # Compatibilidad con resultados CLI: «Receta ID: {json}».
    start=detail.find('{')
    if start<0:return {}
    try:value=json.loads(detail[start:])
    except (ValueError,TypeError):return {}
    return value if isinstance(value,dict) else {}


def present_task(task):
    source=None
    spec=task.get('recipe_spec')
    if isinstance(spec,str):
        try:spec=json.loads(spec)
        except ValueError:spec=None
    if isinstance(spec,dict):source=spec.get('app_source','laboratorio')
    preparing=task['action']=='app_prepare'
    result=preparation_result(task.get('detail','')) if preparing else {}
    source=source or result.get('app_source') or (None if preparing else 'laboratorio')
    try:app=source_profile(source)['name'] if source else 'App no registrada'
    except ValueError:app='App no reconocida'
    label=app+' · '+('Abrir/comprobar' if preparing else 'Likes y scroll' if task['action']=='lab_like_flow' else 'Like' if task['action']=='lab_like' else 'Prueba local')
    status=task['status']
    if preparing and status=='Completado':
        if result.get('foreground_verified') is True:
            status='App abierta'
            if result.get('like_mapping')=='pending':status+=' · Likes pendientes de mapeo'
        else:status='Preparación completada · revisar verificación'
    return dict(app=app,source=source,action_label=label,status_label=status,result=result)


def summarize_batch(tasks):
    if not tasks:return None
    presented=[present_task(task) for task in tasks]
    return dict(batch=tasks[0]['batch'],created=min(t['created'] for t in tasks),devices=len({t['device_id'] for t in tasks}),tasks=len(tasks),states=dict(Counter(t['status'] for t in tasks)),actions=sorted({p['action_label'] for p in presented}),opened=sum(t['action']=='app_prepare' and t['status']=='Completado' and p['result'].get('foreground_verified') is True for t,p in zip(tasks,presented)),mapping_pending=sum(t['action']=='app_prepare' and t['status']=='Completado' and p['result'].get('like_mapping')=='pending' for t,p in zip(tasks,presented)))
