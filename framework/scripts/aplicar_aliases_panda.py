"""Apply fixed Panda names and visual numbers at lab startup."""
import argparse
import asyncio
import json
from pathlib import Path

from core.device_aliases import read_aliases
from core.device_map import load_latest_map
from core.mass_orchestrator import bloquear_granja
from core.panda_api import PandaClient, PandaError
from core.project_env import load_project_environment

ROOT = Path(__file__).resolve().parents[1]
FIXED_SORTS = {'p01': 7, 'p02': 6, 'p03': 22}


def targets(root):
    mapping = load_latest_map(root)
    mapped = {row['plate']: row for row in mapping['plates']} if mapping else {}
    aliases = {row['plate']: row for row in read_aliases(root)}
    result = []
    for plate, sort in FIXED_SORTS.items():
        alias = aliases.get(plate)
        identity = mapped.get(plate)
        if not alias or not identity or alias['device_ref'] != identity['device_ref']:
            raise PandaError(f'{plate}: alias no vinculado al mapa DPAPI')
        result.append((plate, identity['device_serial_plain'], sort, alias['alias']))
    return result


def resolve_targets(rows, desired):
    def matches_sort(row, sort):
        return str(row.get('sort')).isdigit() and int(row['sort']) == sort

    result = {}
    for plate, identity, sort, name in desired:
        matches = [row for row in rows if row.get('onlySerial') == identity]
        if len(matches) != 1:
            raise PandaError(f'{plate}: identidad Panda ausente o ambigua')
        row = matches[0]
        try:
            PandaClient._resolve(rows, str(row.get('sort', '')))
        except (ValueError, PandaError):
            raise PandaError(f'{plate}: vinculacion Panda invalida') from None
        if any(other is not row and matches_sort(other, sort) for other in rows):
            raise PandaError(f'{plate}: numero {sort:02d} ocupado')
        result[plate] = (row['serial'], matches_sort(row, sort) and row.get('name') == name)
    return result


async def reconcile(client, desired, *, apply=False):
    current = resolve_targets(await client.inventario(), desired)
    result = {}
    for plate, _, sort, name in desired:
        transport, aligned = current[plate]
        sent = apply and not aligned
        if sent:
            await client.update_device_alias(transport, sort, name)
            current = resolve_targets(await client.inventario(), desired)
            if not current[plate][1]:
                raise PandaError(f'{plate}: reasignacion sin confirmar en Panda')
        result[plate] = {'sort': sort, 'sent': sent}
    for plate, details in result.items():
        details['aligned'] = current[plate][1]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write changes and verify by reading Panda again')
    args = parser.parse_args()
    try:
        load_project_environment()
        with bloquear_granja(ROOT / 'sessions/farm.lock'):
            result = asyncio.run(reconcile(PandaClient(), targets(ROOT), apply=args.apply))
    except KeyboardInterrupt:
        return 130
    except PandaError as exc:
        print(str(exc))
        return 1
    except (OSError, RuntimeError, ValueError):
        print('No se pudo validar el inventario de Panda')
        return 1
    print(json.dumps(result))
    return 0 if all(item['aligned'] for item in result.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
