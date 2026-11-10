"""Local aliases for the canonical hardware inventory."""
import csv
from contextlib import closing
from pathlib import Path
import re
import sqlite3


INVENTORY = Path('tests/fixtures/csv/lab_stage3.csv')
ALIAS_DB = Path('data/device_aliases.db')


def inventory_aliases(root):
    with (root / INVENTORY).open(encoding='utf-8-sig', newline='') as stream:
        rows = [(row['device_ref'], row['alias'].strip()) for row in csv.DictReader(stream)
                if row.get('estado') == 'vinculado']
    if (not rows or len(rows) != len({ref for ref, _ in rows})
            or any(not re.fullmatch('[0-9a-f]{16}', ref) or not 1 <= len(alias) <= 120
                   or not alias.isprintable() for ref, alias in rows)):
        raise ValueError('Invalid alias inventory')
    return rows


def seed_aliases(root):
    """Import the verified inventory without replacing locally customized aliases."""
    rows = inventory_aliases(root)
    path = root / ALIAS_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS device_aliases (
            device_ref TEXT PRIMARY KEY NOT NULL, alias_personalizado TEXT NOT NULL)''')
        db.executemany('''INSERT INTO device_aliases(device_ref,alias_personalizado) VALUES (?,?)
            ON CONFLICT(device_ref) DO NOTHING''', rows)


def read_aliases(root):
    """Join only enrolled hardware references; the UI never needs Panda or ADB."""
    path = root / ALIAS_DB
    if not path.is_file():
        return []
    refs = [ref for ref, _ in inventory_aliases(root)]
    values = ','.join('(?,?)' for _ in refs)
    params = [value for index, ref in enumerate(refs, 1) for value in (index, ref)]
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        rows = db.execute(f'''WITH enrolled(position,device_ref) AS (VALUES {values})
            SELECT enrolled.position, enrolled.device_ref, aliases.alias_personalizado
            FROM enrolled JOIN device_aliases AS aliases USING(device_ref)
            ORDER BY enrolled.position''', params).fetchall()
    return [{'plate': f'p{position:02d}', 'device_ref': ref, 'alias': alias}
            for position, ref, alias in rows]


if __name__ == '__main__':
    from core.device_map import load_latest_map
    from core.project_env import load_project_environment

    root = Path(__file__).resolve().parents[1]
    load_project_environment()
    mapping = load_latest_map(root)
    by_plate = {row['plate']: row['device_ref'] for row in mapping['plates']} if mapping else {}
    if any(by_plate.get(f'p{index:02d}') != ref
           for index, (ref, _) in enumerate(inventory_aliases(root), 1)):
        raise SystemExit('Alias inventory does not match DPAPI')
    seed_aliases(root)
