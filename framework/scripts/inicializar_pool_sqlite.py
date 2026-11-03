"""Configurar tres perfiles de laboratorio sin abrir navegadores ni crear leases."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def inicializar(database, pool_path, accounts_path):
    from config.proxies import leer_proxy_pool
    from core.diagnostic_bridge import escribir_json
    entries=leer_proxy_pool(pool_path)
    mapping=[{'id':f'cuenta_{i:02d}','proxy':f'192.168.1.199:{8000+i}'} for i in range(1,4)]
    selected=[]
    for account in mapping:
        entry=next((e for e in entries if e['endpoint']==account['proxy']),None)
        if not entry or not entry.get('lab_shared_exit') or not entry.get('exit_ip') or not entry['enabled']:
            raise ValueError('Se requieren los tres endpoints habilitados de laboratorio con IP de salida configurada')
        selected.append((account,entry))
    accounts_path=Path(accounts_path)
    if accounts_path.exists() and json.loads(accounts_path.read_text(encoding='utf-8-sig'))!=mapping:
        raise ValueError('El archivo de cuentas ya tiene otro mapeo; conservar configuración existente')
    with database.conexion() as con:
        con.execute('BEGIN IMMEDIATE')
        for account,entry in selected:
            identity='web:'+account['id']
            if con.execute('''SELECT 1 FROM proxy_reservas WHERE endpoint=? OR id_adb=? LIMIT 1''',
                           (entry['endpoint'],identity)).fetchone():
                raise ValueError('Cerrar las reservas activas o revisar cuarentenas antes de inicializar')
            prior=con.execute('SELECT lab_shared_exit FROM proxy_pool WHERE endpoint=?',(entry['endpoint'],)).fetchone()
            if prior and not prior['lab_shared_exit']:
                raise ValueError('El endpoint existente pertenece a producción')
            binding=con.execute('SELECT * FROM proxy_perfiles WHERE account_id=? OR endpoint=?',
                                (identity,entry['endpoint'])).fetchall()
            if any(b['account_id']!=identity or b['endpoint']!=entry['endpoint'] for b in binding):
                raise ValueError('Existe una asignación fija diferente; no se modificó')
            con.execute('''INSERT INTO proxy_pool(endpoint,host,puerto,exit_ip,habilitado,lab_shared_exit)
                VALUES (?,?,?,?,1,1) ON CONFLICT(endpoint) DO UPDATE SET
                exit_ip=excluded.exit_ip,habilitado=1''',
                (entry['endpoint'],entry['host'],entry['port'],entry['exit_ip']))
            con.execute('INSERT INTO proxy_perfiles VALUES (?,?) ON CONFLICT(account_id) DO NOTHING',
                        (identity,entry['endpoint']))
        # Si falla la escritura, el contexto revierte la transacción de SQLite.
        escribir_json(accounts_path,mapping)
    return mapping


def main():
    from core.database import Database
    from core.mass_orchestrator import bloquear_granja
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path)
    parser.add_argument('--pool',type=Path,default=ROOT/'config/proxy_pool.json')
    parser.add_argument('--accounts',type=Path,default=ROOT/'config/web_accounts.json')
    args=parser.parse_args()
    with bloquear_granja(ROOT/'sessions/farm.lock'):
        inicializar(Database(args.database),args.pool,args.accounts)
    print('[Base de Datos] Pool de simulación local configurado: 3 endpoints listos')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
