"""Validar o ejecutar una receta local sobre identidades elegidas explícitamente."""
import argparse
from pathlib import Path
from granjita.recipes import load_recipe,execute_recipe
from granjita.inventory import FleetStore,scan_fleet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--device-id',action='append',default=[])
    args=parser.parse_args()
    recipe=load_recipe(args.recipe)
    print('Receta válida:',recipe['id'],'· perfil:',recipe['profile'])
    if not args.execute:
        print('Vista previa sin ejecutar acciones. Objetivo:',recipe['objective'])
        return
    if not args.device_id:
        parser.error('La ejecución requiere al menos un --device-id explícito.')
    store=FleetStore()
    store.save_fleet(scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')]))
    candidates={r['id']:r for r in store.fleet_devices() if r['status']=='Validado' and r['identity_state']=='Serial leído'}
    if set(args.device_id)-set(candidates):
        parser.error('Una identidad elegida no está validada o tiene conflicto. No se ejecutó el lote.')
    for result in execute_recipe(recipe,[candidates[k] for k in dict.fromkeys(args.device_id)]):
        print('Tarea',result['task'],result['status'])


if __name__=='__main__':
    main()
