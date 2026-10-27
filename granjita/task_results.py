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


TERMINAL={'Completado','Revisar resultado','Cancelado','Expirado','Interrumpido','Resultado incierto','No ejecutado'}


def summarize_batch(tasks):
    if not tasks:return None
    presented=[present_task(task) for task in tasks]
    states=dict(Counter(t['status'] for t in tasks))
    pending=sum(t['status'] not in TERMINAL for t in tasks)
    finished=pending==0
    if finished:
        label='LOTE TERMINADO'
        if any(states.get(s,0) for s in ('Revisar resultado','Resultado incierto','Interrumpido','No ejecutado','Expirado')):label+=' · Requiere revisión'
        elif states.get('Cancelado'):label+=' · Con cancelaciones'
        else:label+=' · Correcto'
    elif states.get('Ejecutando'):label='LOTE EN EJECUCIÓN'
    elif states.get('Programado'):label='LOTE PROGRAMADO'
    else:label='LOTE PENDIENTE'
    prep=[(t,p) for t,p in zip(tasks,presented) if t['action']=='app_prepare']
    opened={t['device_id'] for t,p in prep if t['status']=='Completado' and p['result'].get('foreground_verified') is True}
    not_executed={t['device_id'] for t,p in prep if t['status'] in ('Cancelado','Expirado','Interrumpido','No ejecutado')}-opened
    unconfirmed={t['device_id'] for t,p in prep if t['status'] in TERMINAL and t['device_id'] not in opened|not_executed}
    return dict(batch=tasks[0]['batch'],created=min(t['created'] for t in tasks),devices=len({t['device_id'] for t in tasks}),tasks=len(tasks),states=states,
        actions=sorted({p['action_label'] for p in presented}),opened=len(opened),opening_unconfirmed=len(unconfirmed),not_executed=len(not_executed),preparation=bool(prep),
        pending=pending,finished=finished,completion_label=label,
        mapping_pending=len({t['device_id'] for t,p in prep if t['status']=='Completado' and p['result'].get('like_mapping')=='pending'}))


def batch_text(batch):
    if not batch:return 'Sin ejecuciones registradas.'
    text=batch['completion_label']+'\n'
    text+=f"{batch['created'][:10]} {batch['created'][11:19]} GT · {batch['devices']} dispositivos · {', '.join(batch['actions'])}\n"
    if batch['preparation']:
        text+=f"Apps abiertas: {batch['opened']} de {batch['devices']} · Sin apertura confirmada: {batch['opening_unconfirmed']} · Sin ejecutar: {batch['not_executed']} · Pendientes: {batch['pending']}\n"
        if batch['mapping_pending']:text+=f"Likes pendientes de mapeo en {batch['mapping_pending']} dispositivos. Abrir la app no ejecuta likes.\n"
    else:text+=f"Tareas pendientes: {batch['pending']} · "
    return text+' · '.join(f'{key}: {value}' for key,value in batch['states'].items())
