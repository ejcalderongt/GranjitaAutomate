"""Importar declaración privada {numero_panda: booleano} con identidad inequívoca."""
import argparse,json
from granjita.inventory import FleetStore
from granjita.physical import ordered_rows
from granjita.panda_api import list_devices
from granjita.app_inventory import AppInventory


def resolve_entries(mapping,devices,rows):
    entries=[]
    for key,present in mapping.items():
        if not str(key).isdigit() or type(present) is not bool:raise ValueError('Número/estado inválidos.')
        number=int(key)
        matches=[d for d in devices if str(d.get('sort','')).isdigit() and int(d['sort'])==number]
        if len(matches)!=1 or not matches[0].get('onlySerial'):raise ValueError(f'Panda {number}: identidad no inequívoca.')
        candidates=[r for r in rows if r.get('hardware_serial')==matches[0]['onlySerial']]
        if len(candidates)!=1:raise ValueError(f'Panda {number}: ficha no inequívoca.')
        entries.append((candidates[0],present,number))
    return entries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file');parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with open(args.file,encoding='utf-8-sig') as stream:mapping=json.load(stream)
    if not isinstance(mapping,dict):parser.error('Se requiere un objeto número: booleano.')
    store=FleetStore();rows=ordered_rows(store.fleet_devices(),store.positions())
    entries=resolve_entries(mapping,list_devices(),rows)
    print(json.dumps(dict(total=len(entries),with_account=sum(v for r,v,n in entries),without_account=sum(not v for r,v,n in entries),applied=args.apply)))
    if args.apply:
        from granjita.core import DATA
        from granjita.app_inventory import audit_stamp
        store.backup(DATA/('granjita-antes-declaracion-'+audit_stamp().replace(':','').replace('.','')+'.sqlite3'))
        print('Registros guardados:',AppInventory(store).declare_batch(entries,'tiktok','user_report'))


if __name__=='__main__':main()
