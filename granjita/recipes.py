"""Recetas declarativas con acciones tipadas, sin shell ni código arbitrario."""
import json
import re
from .core import ROOT
from .automation import PACKAGE,JobStore,run_lab


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
    if recipe.get('action')!='lab_smoke':
        raise ValueError('Esta versión solo ejecuta la acción local lab_smoke.')
    context=recipe.get('context',{})
    object_keys(context,{'environment','audience','intent'},'contexto')
    if context.get('environment')!='local_lab' or any(not isinstance(v,str) or len(v)>1000 for v in context.values()):
        raise ValueError('Contexto de laboratorio inválido.')
    object_keys(recipe.get('parameters'),{'comment'},'parámetros')
    comment=recipe['parameters'].get('comment')
    if not isinstance(comment,str) or not 1<=len(comment.strip())<=280:
        raise ValueError('El comentario debe tener entre 1 y 280 caracteres.')
    if recipe.get('execution')!={'concurrency':1,'automatic_retries':0,'on_uncertain':'review'}:
        raise ValueError('La ejecución inicial es secuencial, sin reintentos automáticos y con revisión de incertidumbre.')
    profile_path=ROOT/'profiles'/(recipe['profile']+'.json')
    profile=json.loads(profile_path.read_text(encoding='utf-8'))
    if profile.get('schema_version')!=1 or profile.get('id')!=recipe['profile'] or profile.get('app_package')!=PACKAGE or profile.get('execution_engine')!='appium' or profile.get('permissions')!='manual_review':
        raise ValueError('Perfil incompatible con el laboratorio.')
    return dict(recipe,_profile_snapshot=profile)


def execute_recipe(recipe,rows):
    jobs=JobStore()
    tasks=jobs.create(rows,recipe['parameters']['comment'])
    jobs.attach_recipe([task['id'] for task in tasks],recipe)
    results=[]
    for task in tasks:
        jobs.update(task['id'],'Ejecutando',f"Receta {recipe['id']}")
        try:
            detail=run_lab(task['row'],task['comment'],task['id'])
            status='Completado'
        except Exception as exc:
            detail=str(exc)
            status='Revisar resultado'
        jobs.update(task['id'],status,f"Receta {recipe['id']}: {detail}")
        results.append(dict(task=task['id'],status=status))
    return results
