"""Recetas declarativas con acciones tipadas, sin shell ni código arbitrario."""
import json
import re
from .core import ROOT
from .automation import PACKAGE,JobStore,run_lab,run_like


def object_keys(value,allowed,label):
    if not isinstance(value,dict) or set(value)-set(allowed):
        raise ValueError('Campos no admitidos en '+label)


def load_recipe(path):
    if path.stat().st_size>65536:
        raise ValueError('La receta excede 64 KB.')
    recipe=json.loads(path.read_text(encoding='utf-8'))
    object_keys(recipe,{'schema_version','id','name','profile','objective','context','action','parameters','execution'},'receta')
    if type(recipe.get('schema_version')) is not int or recipe['schema_version']!=1:
        raise ValueError('Versión de receta no admitida.')
    for key in ['id','profile']:
        if not isinstance(recipe.get(key),str) or not re.fullmatch('[a-z0-9][a-z0-9_.-]{0,63}',recipe[key]):
            raise ValueError('Identificador de receta/perfil inválido.')
    for key in ['name','objective']:
        if not isinstance(recipe.get(key),str) or not 1<=len(recipe[key])<=1000:
            raise ValueError('Nombre u objetivo inválido.')
    if recipe.get('action') not in ('lab_smoke','lab_like','lab_like_flow'):
        raise ValueError('Solo se admiten acciones del laboratorio local.')
    context=recipe.get('context',{})
    object_keys(context,{'environment','audience','intent'},'contexto')
    if context.get('environment')!='local_lab' or any(not isinstance(v,str) or len(v)>1000 for v in context.values()):
        raise ValueError('Contexto de laboratorio inválido.')
    if recipe['action']=='lab_like_flow':
        from .taskflow import validate_parameters
        validate_parameters(recipe.get('parameters'))
    elif recipe['action']=='lab_like':
        if recipe.get('parameters')!={'target':'lab_like_01','desired_state':True} or type(recipe['parameters']['desired_state']) is not bool:
            raise ValueError('El flujo de likes solo marca lab_like_01 en la aplicación local.')
    else:
        object_keys(recipe.get('parameters'),{'comment'},'parámetros')
        comment=recipe['parameters'].get('comment')
        if not isinstance(comment,str) or not 1<=len(comment.strip())<=280:
            raise ValueError('El comentario debe tener entre 1 y 280 caracteres.')
    if recipe.get('execution')!={'concurrency':1,'automatic_retries':0,'on_uncertain':'review'} or type(recipe['execution']['concurrency']) is not int or type(recipe['execution']['automatic_retries']) is not int:
        raise ValueError('La ejecución inicial es secuencial, sin reintentos automáticos y con revisión de incertidumbre.')
    profile_path=ROOT/'profiles'/(recipe['profile']+'.json')
    profile=json.loads(profile_path.read_text(encoding='utf-8'))
    object_keys(profile,{'schema_version','id','name','desired_packages','identity','permissions','execution_engine','app_package','adb','note'},'perfil')
    if type(profile.get('schema_version')) is not int or profile['schema_version']!=1 or profile.get('id')!=recipe['profile'] or profile.get('app_package')!=PACKAGE or profile.get('execution_engine')!='appium' or profile.get('permissions')!='manual_review':
        raise ValueError('Perfil incompatible con el laboratorio.')
    return dict(recipe,_profile_snapshot=profile)


def execute_recipe(recipe,rows):
    jobs=JobStore()
    flow=recipe['action']=='lab_like_flow'
    like=recipe['action']=='lab_like'
    tasks=jobs.create(rows,recipe['parameters'].get('comment',''), 'lab_like_flow' if flow else 'lab_like' if like else 'lab_like_comment_scroll',recipe['parameters'] if flow else None)
    jobs.attach_recipe([task['id'] for task in tasks],recipe)
    results=[]
    for task in tasks:
        if flow:
            from .taskflow import window_state
            if window_state(recipe['parameters'])!='ready':
                jobs.update(task['id'],'No ejecutado','La CLI solo ejecuta dentro del horario; usa el panel para esperar el inicio.')
                results.append(dict(task=task['id'],status='No ejecutado'))
                continue
        jobs.update(task['id'],'Ejecutando',f"Receta {recipe['id']}")
        try:
            if flow:
                from .taskflow import run_flow
                detail=run_flow(task['row'],task['id'],recipe['parameters'],audit=lambda kind,data:jobs.like_event(task['id'],kind,data))
            else:detail=run_like(task['row'],task['id'],audit=lambda kind,data:jobs.like_event(task['id'],kind,data)) if like else run_lab(task['row'],task['comment'],task['id'])
            status='Completado'
        except Exception as exc:
            detail=str(exc)
            status='Revisar resultado'
        jobs.update(task['id'],status,f"Receta {recipe['id']}: {detail}")
        results.append(dict(task=task['id'],status=status))
    return results
