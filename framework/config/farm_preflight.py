"""Synthetic checks only. No transport, browser, proxy or hardware adapters."""
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import re


@dataclass(frozen=True)
class ConstraintVerdict:
    constraint: str
    status: str
    reason: str
    counters: dict

    def __post_init__(self):
        if (self.constraint not in ('C1', 'C2', 'C3', 'C4', 'C5')
                or self.status not in ('PASS', 'WARN', 'FAIL')
                or not re.fullmatch(self.constraint + r' [A-Z_]+ \| alternativa: [A-Za-z_ ]+', self.reason)
                or len(self.reason) > 200 or not self.reason.isascii()
                or not isinstance(self.counters, dict)
                or any(not re.fullmatch(r'[a-z_]+', k) or type(v) is not int or v < 0
                       for k, v in self.counters.items())):
            raise ValueError('Veredicto sintetico invalido')


def load_synthetic_fixture(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Fixture sintetico invalido')
    ctx = json.loads(path.read_text(encoding='ascii'))
    if ctx.get('synthetic') is not True or not isinstance(ctx.get('devices'), list):
        raise ValueError('Fixture sintetico invalido')
    return ctx


def verdict(constraint, failed, missing, counters):
    status = 'FAIL' if failed else 'WARN' if missing else 'PASS'
    detail = {'FAIL': 'DATOS_NO_CUMPLEN', 'WARN': 'DATOS_INCOMPLETOS', 'PASS': 'SINTETICO_VALIDO'}[status]
    return ConstraintVerdict(constraint, status,
        constraint + ' ' + detail + ' | alternativa: revisar fixture sintetico', counters)


def records(devices, ctx, key):
    if (ctx.get('synthetic') is not True or not isinstance(devices, list)
            or any(not isinstance(device, str) or not re.fullmatch(r'p[0-9]{2}', device) for device in devices)):
        raise ValueError('Fixture sintetico invalido')
    if not isinstance(ctx.get(key, {}), dict):
        raise ValueError('Fixture sintetico invalido')
    return [ctx.get(key, {}).get(device) for device in devices]


async def evaluate_c1(devices, policy, ctx):
    rows = records(devices, ctx, 'c1')
    missing = sum(not isinstance(row, dict) or any(type(row.get(k)) is not bool for k in ('authorized', 'connected')) for row in rows)
    failed = sum(isinstance(row, dict) and (row.get('authorized') is False or row.get('connected') is False) for row in rows)
    failed += int(not devices or len(devices) != policy.stage or len(set(devices)) != len(devices))
    return verdict('C1', failed, missing, {'checked': len(rows), 'failed': failed, 'missing': missing})


async def evaluate_c2(devices, policy, ctx):
    rows = records(devices, ctx, 'c2')
    target = policy.country or ctx.get('target_country')
    missing = sum(not isinstance(row, dict) or not isinstance(row.get('country'), str)
                  or not re.fullmatch('[A-Z]{2}', row['country'])
                  or any(type(row.get(k)) is not bool for k in ('geo_resolved', 'direct_leak')) for row in rows)
    missing += int(not isinstance(target, str) or not re.fullmatch('[A-Z]{2}', target))
    failed = sum(isinstance(row, dict) and (row.get('direct_leak') is True
                 or row.get('geo_resolved') is False
                 or row.get('country') is not None and target and row['country'] != target) for row in rows)
    return verdict('C2', failed, missing, {'checked': len(rows), 'failed': failed, 'missing': missing})


async def evaluate_c3(devices, policy, ctx):
    rows = records(devices, ctx, 'c3')
    valid = [row.get('hold_seconds') if isinstance(row, dict) else None for row in rows]
    missing = sum(type(value) not in (int, float) for value in valid)
    failed = sum(type(value) in (int, float) and not policy.hold_min <= value <= policy.hold_max for value in valid)
    return verdict('C3', failed, missing, {'checked': len(rows), 'failed': failed, 'missing': missing})


async def evaluate_c4(devices, policy, ctx):
    rows = records(devices, ctx, 'c4')
    missing = sum(not isinstance(row, dict) or not isinstance(row.get('lease'), str) or not row['lease']
                  or any(type(row.get(k)) is not bool for k in ('available', 'rotation_ok')) for row in rows)
    leases = [row['lease'] for row in rows if isinstance(row, dict) and isinstance(row.get('lease'), str)]
    failed = len(leases) - len(set(leases))
    failed += sum(isinstance(row, dict) and (row.get('available') is False or row.get('rotation_ok') is False) for row in rows)
    return verdict('C4', failed, missing, {'checked': len(rows), 'failed': failed, 'missing': missing})


def metrics(devices, ctx):
    rows = records(devices, ctx, 'c5')
    names = ('captcha_count', 'softblock_count', 'logout_count')
    missing = sum(not isinstance(row, dict) or any(type(row.get(k)) is not int or row[k] < 0 for k in names) for row in rows)
    totals = {name: sum(row[name] for row in rows if isinstance(row, dict) and type(row.get(name)) is int and row[name] >= 0) for name in names}
    return missing, totals


async def evaluate_c5(devices, policy, ctx):
    missing, totals = metrics(devices, ctx)
    return verdict('C5', sum(totals.values()), missing, {'checked': len(devices), 'missing': missing, **totals})


def decide(verdicts, policy):
    if [v.constraint for v in verdicts] != ['C1', 'C2', 'C3', 'C4', 'C5']:
        raise ValueError('Veredictos incompletos')
    if any(v.status == 'FAIL' for v in verdicts) and policy.abort_on_fail:
        return 'abort'
    if any(v.status == 'WARN' for v in verdicts) and policy.abort_on_warn:
        return 'abort'
    return 'proceed_with_warnings' if any(v.status != 'PASS' for v in verdicts) else 'proceed'


def migrate(db):
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS farm_preflight_runs (id TEXT PRIMARY KEY, run_id TEXT, stage INT, started_at TEXT, finished_at TEXT, decision TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS farm_preflight_verdicts (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, "constraint" TEXT, status TEXT, reason TEXT, counters_json TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS farm_stage_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, stage INT, captcha_count INT, softblock_count INT, logout_count INT, recorded_at TEXT)')


def now():
    return datetime.now(timezone.utc).isoformat()


async def run_farm_preflight(devices, policy, ctx, db):
    run_id = ctx.get('run_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', run_id) or ctx.get('synthetic') is not True:
        raise ValueError('Fixture sintetico invalido')
    migrate(db)
    with db:
        db.execute('INSERT INTO farm_preflight_runs VALUES (?, ?, ?, ?, NULL, NULL)', (run_id, run_id, policy.stage, now()))
    verdicts = []
    try:
        for evaluate in (evaluate_c1, evaluate_c2, evaluate_c3, evaluate_c4, evaluate_c5):
            await asyncio.sleep(0)
            item = await evaluate(devices, policy, ctx)
            verdicts.append(item)
            with db:
                db.execute('INSERT INTO farm_preflight_verdicts (run_id, "constraint", status, reason, counters_json) VALUES (?, ?, ?, ?, ?)',
                    (run_id, item.constraint, item.status, item.reason, json.dumps(item.counters, ensure_ascii=True)))
        decision = decide(verdicts, policy)
        _, totals = metrics(devices, ctx)
        with db:
            db.execute('INSERT INTO farm_stage_metrics (run_id, stage, captcha_count, softblock_count, logout_count, recorded_at) VALUES (?, ?, ?, ?, ?, ?)',
                (run_id, policy.stage, totals['captcha_count'], totals['softblock_count'], totals['logout_count'], now()))
            db.execute('UPDATE farm_preflight_runs SET finished_at=?, decision=? WHERE id=?', (now(), decision, run_id))
        return verdicts
    except (KeyboardInterrupt, asyncio.CancelledError):
        with db:
            db.execute('DELETE FROM farm_preflight_verdicts WHERE run_id=?', (run_id,))
            db.execute('UPDATE farm_preflight_runs SET finished_at=?, decision=? WHERE id=?', (now(), 'cancelled', run_id))
        raise


def write_evidence(root, run_id, policy, verdicts, code, cancelled=False):
    report = {'timestamp': now(), 'run_id': run_id, 'synthetic': True,
              'policy': asdict(policy) if policy else None,
              'decision': 'cancelled' if cancelled else decide(verdicts, policy) if verdicts else 'precheck_failed',
              'cancelled': cancelled, 'verdicts': [] if cancelled else [asdict(v) for v in verdicts],
              'exit_code': code, 'warnings': ['Synthetic evidence does not authorize hardware execution.']}
    path = root / 'runs' / ('farm_preflight_' + run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='ascii')
    return path
