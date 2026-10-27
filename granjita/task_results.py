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
    verification=task.get('verification_payload')
    if isinstance(verification,str):verification=preparation_result(verification)
    verification=verification or {}
    labels={'open':'Abierta en primer plano','not_foreground':'No está en primer plano','unconfirmed':'No se pudo comprobar','error':'No se pudo comprobar','not_executed':'Sin ejecutar','cancelled':'Verificación cancelada'}
    verification_label=labels.get(verification.get('state'),'Pendiente / sin comprobar') if preparing else 'No aplica'
    if verification.get('at'):verification_label+=' · '+verification['at'][11:19]+' GT'
    return dict(app=app,source=source,action_label=label,status_label=status,result=result,verification=verification,verification_label=verification_label)


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
        actions=sorted({p['action_label'] for p in presented}),apps=sorted({p['app'] for p in presented}),verification_at=max((p['verification'].get('at','') for p in presented),default=''),opened=len(opened),opening_unconfirmed=len(unconfirmed),not_executed=len(not_executed),preparation=bool(prep),
        pending=pending,finished=finished,completion_label=label,
        verification_total=len(prep),verification_checked=sum(bool(p['verification']) for t,p in prep),
        verification_states=dict(Counter(p['verification'].get('state','pending') for t,p in prep)),
        mapping_pending=len({t['device_id'] for t,p in prep if t['status']=='Completado' and p['result'].get('like_mapping')=='pending'}))


def batch_text(batch):
    if not batch:return 'Sin ejecuciones registradas.'
    text=batch['completion_label']+'\n'
    text+=f"{batch['created'][:10]} {batch['created'][11:19]} GT · {batch['devices']} dispositivos · {', '.join(batch['actions'])}\n"
    if batch['preparation']:
        text+=f"Apps abiertas: {batch['opened']} de {batch['devices']} · Sin apertura confirmada: {batch['opening_unconfirmed']} · Sin ejecutar: {batch['not_executed']} · Pendientes: {batch['pending']}\n"
        if batch['mapping_pending']:text+=f"Likes pendientes de mapeo en {batch['mapping_pending']} dispositivos. Abrir la app no ejecuta likes.\n"
    else:text+=f"Tareas pendientes: {batch['pending']} · "
    if batch['preparation']:
        checks=batch['verification_states']
        text+=f"Verificación posterior procesada: {batch['verification_checked']} de {batch['verification_total']} · Abiertas ahora: {checks.get('open',0)} · No en primer plano: {checks.get('not_foreground',0)} · Sin comprobar: {checks.get('unconfirmed',0)+checks.get('error',0)+checks.get('pending',0)} · Sin ejecutar: {checks.get('not_executed',0)} · Comprobación cancelada: {checks.get('cancelled',0)}\n"
        if batch['verification_checked']==batch['verification_total']:text+='VERIFICACIÓN POSTERIOR TERMINADA · '
        else:text+='VERIFICACIÓN POSTERIOR PENDIENTE · '
    return text+' · '.join(f'{key}: {value}' for key,value in batch['states'].items())


def compact_batch(batch,verifying=False):
    """Tres cifras visibles; la explicación completa permanece en tooltip y tabla."""
    from html import escape
    if not batch:return dict(html='<b>Sin ejecuciones registradas</b>',status='Sin ejecuciones registradas.',review=0)
    finished=batch['finished']
    title='Verificando ejecución…' if verifying else 'Lote terminado' if finished else 'Lote en ejecución' if batch['states'].get('Ejecutando') else 'Lote programado' if batch['states'].get('Programado') else 'Lote pendiente'
    apps=', '.join(batch.get('apps',[])) or 'Aplicación'
    checks=batch['verification_states']
    checked=batch['verification_checked']
    total=batch['verification_total']
    if batch['preparation']:
        confirmed=checks.get('open',0) if checked else batch['opened']
        review=sum(checks.get(state,0) for state in ('error','unconfirmed','not_foreground','cancelled')) if checked else batch['opening_unconfirmed']
        caption='Apps verificadas' if checked else 'Aperturas confirmadas'
        skipped=batch['not_executed']
    else:
        confirmed=batch['states'].get('Completado',0)
        review=sum(batch['states'].get(state,0) for state in ('Revisar resultado','Resultado incierto'))
        skipped=sum(batch['states'].get(state,0) for state in ('Cancelado','Expirado','Interrumpido','No ejecutado'))
        caption='Completadas'
    if batch['preparation']:
        footer='Verificando: '+str(checked)+' de '+str(total) if verifying or checked<total else 'Verificación terminada'
    else:footer='Ejecución terminada' if finished else str(batch['pending'])+' tareas pendientes'
    at=batch.get('verification_at') or batch['created']
    footer+=' · '+at[11:19]+' GT'
    status=f"{title} · {apps} · {confirmed}/{batch['devices']} {caption.lower()} · {review} para revisar · {skipped} sin ejecutar · {footer}"
    cells=[]
    for value,label in [(str(confirmed)+' / '+str(batch['devices']),caption),(str(review),'Para revisar'),(str(skipped),'Sin ejecutar')]:
        cells.append('<td width="33%"><span style="font-size:24px;font-weight:700">'+escape(value)+'</span><br><span style="font-size:13px;font-weight:400">'+escape(label)+'</span></td>')
    html='<b>'+escape(title+' · '+apps)+'</b><table width="100%" cellspacing="3"><tr>'+''.join(cells)+'</tr></table><span style="font-size:12px;font-weight:400">'+escape(footer)+'</span>'
    return dict(html=html,status=status,review=review,confirmed=confirmed,skipped=skipped)
