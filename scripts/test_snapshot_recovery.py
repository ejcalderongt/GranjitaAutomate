"""Prueba real de recuperación: solo crea/elimina un archivo propio de nombre aleatorio."""
import argparse,json,uuid
from granjita.inventory import FleetStore,scan_fleet
from granjita.snapshots import eligible,read_file,write_missing,capture,restore,query,DIRECTORY


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device-id',required=True);args=parser.parse_args()
    store=FleetStore();store.save_fleet(scan_fleet([int(p) for p in store.setting('ports','5037,5038').split(',')]))
    rows=[r for r in eligible(store) if r['id']==args.device_id]
    if len(rows)!=1:raise ValueError('Identidad no elegible.')
    row=rows[0];name='recovery-proof-'+uuid.uuid4().hex[:12]+'.json'
    data=json.dumps(dict(test='Granjita 4.2',nonce=uuid.uuid4().hex)).encode()
    if read_file(row,name) is not None:raise ValueError('Nombre ya existente.')
    write_missing(row,name,data)
    identifier,state=capture(store,row)
    if state!='Completo':raise RuntimeError('Snapshot parcial: no se elimina el archivo de prueba.')
    if read_file(row,name)!=data:raise RuntimeError('El archivo cambió; no eliminar.')
    query(row,'rm '+DIRECTORY+'/'+name)
    result=restore(store,row)
    assert read_file(row,name)==data,'Contenido restaurado incorrecto'
    print(json.dumps(dict(snapshot=identifier,proof_file=name,result=result,verified=True),ensure_ascii=False))

if __name__=='__main__':main()
