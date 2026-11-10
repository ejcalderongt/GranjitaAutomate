"""Sanitized status snapshots shared by the CLI and the local dashboard."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

NETWORK_OK = {'https_ok', 'ping_ok'}
NETWORK_STATES = NETWORK_OK | {'identity_unverified', 'network_failed'}
PROFILE_FIELDS = ('app', 'locale', 'timezone')
RATES = {'gpt-4o-mini': (0.15, 0.075, 0.60), 'gpt-4o': (2.50, 1.25, 10.00)}
STATES = {'preflight', 'running', 'completed', 'blocked', 'cancelled', 'incident'}


def estimated_cost(observations):
    total = 0.0
    for row in observations:
        if not row.get('api_called'):
            continue
        rates = RATES.get(row.get('model'))
        input_tokens, cached, output_tokens = (row.get(k) for k in
            ('input_tokens', 'cached_input_tokens', 'output_tokens'))
        cached = 0 if cached is None else cached
        if (rates is None or any(type(v) is not int or v < 0
                                 for v in (input_tokens, cached, output_tokens)) or cached > input_tokens):
            return None
        total += ((input_tokens - cached) * rates[0] + cached * rates[1] + output_tokens * rates[2]) / 1e6
    return round(total, 8)


def write_status(root, run_id, report):
    directory = root / 'runs'
    directory.mkdir(exist_ok=True)
    path = directory / f'lab_status_{run_id}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=True), encoding='ascii')
    temporary.replace(path)


def read_dashboard(root, inventory):
    reports = []
    for path in sorted((Path(root) / 'runs').glob('lab_status_*.json'), reverse=True):
        try:
            if path.is_symlink() or path.stat().st_size > 65536:
                continue
            raw = json.loads(path.read_text(encoding='ascii'))
            stamp = datetime.fromisoformat(raw['checked_at'])
            if stamp.tzinfo is None or raw['state'] not in STATES or not isinstance(raw['devices'], list):
                continue
            cost = raw.get('estimated_usd')
            cost = cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None
            reports.append((stamp, raw['state'], raw.get('started') is True, cost, raw['devices']))
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            continue
    reports.sort(key=lambda report: report[0], reverse=True)
    latest = reports[0] if reports else None
    rows = {item['device_ref']: {**item, 'network': 'unchecked', 'last_run': None} for item in inventory}
    if latest:
        for item in latest[4]:
            if not isinstance(item, dict):
                continue
            ref, plate, network = (item.get(k) for k in ('device_ref', 'plate', 'network'))
            if (not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{16}', ref)
                    or not isinstance(plate, str) or not re.fullmatch('p[0-9]{2}', plate)
                    or not isinstance(network, str) or network not in NETWORK_STATES):
                continue
            alias = item.get('alias')
            alias = alias if isinstance(alias, str) and alias.isprintable() and len(alias) <= 200 else plate
            rows.setdefault(ref, {'device_ref': ref, 'plate': plate, 'alias': alias, 'last_run': None})
            rows[ref]['network'] = network
            for field in PROFILE_FIELDS:
                value = item.get(field)
                rows[ref][field] = value if value in ('ok', 'manual') else 'unchecked'
    for stamp, _, started, _, checked_devices in reports:
        if started:
            for item in checked_devices:
                if not isinstance(item, dict) or item.get('network') not in ('https_ok', 'ping_ok'):
                    continue
                ref = item.get('device_ref')
                if isinstance(ref, str) and ref in rows and rows[ref]['last_run'] is None:
                    rows[ref]['last_run'] = stamp.isoformat()
    devices = sorted(rows.values(), key=lambda row: row['plate'])
    online = sum(row['network'] in NETWORK_OK | {'network_failed'} for row in devices)
    network_ok = sum(row['network'] in NETWORK_OK for row in devices)
    state = latest[1] if latest else 'unchecked'
    return {'state': state, 'online': online if latest else None,
            'ready': network_ok if state in ('running', 'completed') else 0 if latest else None,
            'alerts': sum(row['network'] in NETWORK_STATES - NETWORK_OK
                          or any(row.get(field)=='manual' for field in PROFILE_FIELDS)
                          for row in devices)
                + int(state in ('blocked', 'incident', 'cancelled')),
            'estimated_usd': latest[3] if latest else None,
            'checked_at': latest[0].isoformat() if latest else None,
            'devices': devices}


def current_timestamp():
    return datetime.now(timezone.utc).isoformat()
