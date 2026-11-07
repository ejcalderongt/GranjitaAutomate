"""Synthetic checks only. No transport, browser, proxy or hardware adapters."""
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import re

DEVICE_PROBE_TIMEOUT_SECONDS = 8
DISCOVERY_TIMEOUT_SECONDS = 12
C4_MUESTRAS_MINIMAS = 3
C4_TIMEOUT_SEGUNDOS = 15
C4_TIMEOUT_GLOBAL_SEGUNDOS = 60
C1_DIAGNOSTIC_KEYS = (
    'missing_authorized', 'missing_connected', 'negative_uid_privileged',
    'negative_emulator_hint', 'negative_automation_apps',
    'integrity_probe_available', 'integrity_probe_errors', 'skipped',
)
C2_DIAGNOSTIC_KEYS = (
    'missing_sim_country', 'missing_locale', 'missing_timezone',
    'mismatch_sim_country', 'mismatch_locale', 'mismatch_timezone',
)
C4_ERROR_MAP = {
    'transport_error': 'transport', 'auth_error': 'auth',
    'http_rejected': 'http_rejected', 'json_invalid': 'json_invalid',
    'not_public': 'not_public', 'other': 'other',
}
C4_ERROR_KINDS = ('transport', 'auth', 'http_rejected', 'json_invalid', 'not_public', 'other')


def c4_diagnostics(result, details=None):
    """Accept only bounded, aggregate-consistent diagnostic records from ctx."""
    empty = {'attempts': result['total'], 'data_available': False,
             'errors_by_kind': dict.fromkeys(C4_ERROR_KINDS, 0),
             'distinct_per_attempt': [], 'latency_ms_by_attempt': []}
    if not isinstance(details, list) or len(details) != result['total'] or len(details) > 32:
        return empty
    kinds = dict.fromkeys(C4_ERROR_KINDS, 0)
    distinct, latencies, timeouts = [], [], 0
    for row in details:
        if (not isinstance(row, dict) or set(row) != {'code', 'new_exit', 'latency_ms'}
                or not isinstance(row['code'], str)
                or row['code'] not in (*C4_ERROR_MAP, 'success', 'timeout')
                or type(row['new_exit']) is not bool
                or type(row['latency_ms']) is not int or row['latency_ms'] < 0
                or row['new_exit'] and row['code'] != 'success'):
            return empty
        if row['code'] in C4_ERROR_MAP:
            kinds[C4_ERROR_MAP[row['code']]] += 1
        timeouts += int(row['code'] == 'timeout')
        distinct.append(row['new_exit'])
        latencies.append(row['latency_ms'])
    if sum(kinds.values()) != result['errors'] or timeouts != result['timeouts'] or sum(distinct) != result['distinct']:
        return empty
    return {'attempts': result['total'], 'data_available': True, 'errors_by_kind': kinds,
            'distinct_per_attempt': distinct, 'latency_ms_by_attempt': latencies}


def diagnostic_defaults(constraint, counters):
    if constraint == 'C1':
        return dict.fromkeys(C1_DIAGNOSTIC_KEYS, 0)
    if constraint == 'C2':
        return {**dict.fromkeys(C2_DIAGNOSTIC_KEYS, 0), 'proxy_verified': False, 'proxy_skipped': False}
    if constraint == 'C4':
        result = {key: counters.get(key, 0) for key in ('total', 'distinct', 'errors', 'timeouts')}
        return {**result, **c4_diagnostics(result)}
    return {}


def real_verdict(constraint, status, action, **counters):
    detail = {'PASS': 'DATOS_ACREDITADOS', 'WARN': 'DATOS_INCOMPLETOS', 'FAIL': 'DATOS_NO_CUMPLEN'}[status]
    return ConstraintVerdict(constraint, status,
        constraint + ' ' + detail + ' | alternativa: ' + action, counters)


async def probe(ctx, name, device):
    connector = ctx.get(name)
    if connector is None:
        return {}
    try:
        result = await asyncio.wait_for(connector(device), timeout=DEVICE_PROBE_TIMEOUT_SECONDS)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


async def evaluate_c1_real(devices, policy, ctx):
    async def inspect(device):
        connector = ctx.get('integrity_probe')
        if connector is None:
            return {}, True
        try:
            row = await asyncio.wait_for(connector(device), timeout=DEVICE_PROBE_TIMEOUT_SECONDS)
            return row if isinstance(row, dict) else {}, False
        except Exception:
            return {}, False
    observations = await asyncio.gather(*(inspect(device) for device in devices))
    rows = [row for row, _ in observations]
    diagnostics = dict.fromkeys(C1_DIAGNOSTIC_KEYS, 0)
    diagnostics['skipped'] = sum(skipped for _, skipped in observations)
    missing = int(len(devices) != policy.stage)
    negative = 0
    for row in rows:
        names = ('root_detected', 'emulator_detected', 'automation_detected', 'play_integrity')
        missing += int(any(type(row.get(name)) is not bool for name in names))
        negative += int(any(row.get(name) is True for name in names[:3]) or row.get('play_integrity') is False)
        diagnostics['missing_authorized'] += int(type(row.get('authorized')) is not bool)
        diagnostics['missing_connected'] += int(type(row.get('connected')) is not bool)
        diagnostics['negative_uid_privileged'] += int(row.get('root_detected') is True)
        diagnostics['negative_emulator_hint'] += int(row.get('emulator_detected') is True)
        diagnostics['negative_automation_apps'] += int(row.get('automation_detected') is True)
        available = type(row.get('play_integrity')) is bool
        diagnostics['integrity_probe_available'] += int(available)
        diagnostics['integrity_probe_errors'] += int(not available)
    status = 'FAIL' if negative else 'WARN' if missing or not devices else 'PASS'
    return real_verdict('C1', status, 'acreditar integridad Android por canal autorizado',
                        checked=len(rows), missing=missing, negative=negative, **diagnostics)


def timezone_country(value):
    try:
        from importlib.resources import files
        text = files('tzdata').joinpath('zoneinfo/zone.tab').read_text(encoding='utf-8')
        for line in text.splitlines():
            fields = line.split()
            if len(fields) >= 3 and not line.startswith('#') and fields[2] == value:
                return fields[0] if re.fullmatch('[A-Z]{2}', fields[0]) else None
    except (ImportError, OSError, UnicodeError):
        pass
    return None


async def evaluate_c2_real(devices, policy, ctx, proxy_manager):
    rows = await asyncio.gather(*(probe(ctx, 'identity_probe', device) for device in devices))
    missing = int(not policy.country or len(devices) != policy.stage)
    mismatches = 0
    diagnostics = dict.fromkeys(C2_DIAGNOSTIC_KEYS, 0)
    for row in rows:
        sim = row.get('sim_country', '')
        countries = [v.upper() for v in sim.split(',') if v] if isinstance(sim, str) else []
        locale = row.get('locale', '')
        match = re.search(r'[_-]([A-Za-z]{2})$', locale) if isinstance(locale, str) else None
        zone = timezone_country(row.get('timezone'))
        values = [countries, [match[1].upper()] if match else [], [zone] if zone else []]
        for field, values_for_field in zip(('sim_country', 'locale', 'timezone'), values):
            if not values_for_field or any(not re.fullmatch('[A-Z]{2}', value) for value in values_for_field):
                missing += 1
                diagnostics['missing_' + field] += 1
            elif policy.country and any(value != policy.country for value in values_for_field):
                mismatches += 1
                diagnostics['mismatch_' + field] += 1
    country = getattr(proxy_manager, '_panda_country', '')
    verified = ctx.get('proxy_preflight_verified') is True
    reused = verified and bool(country) and (not policy.country or country.upper() == policy.country)
    skipped = not verified and proxy_manager is None
    if not verified and proxy_manager is not None:
        try:
            await asyncio.wait_for(proxy_manager.verificar_preflight(run_id=ctx['run_id']), timeout=90)
            verified = True
        except Exception:
            verified = False
    if not verified or not country:
        missing += 1
    elif policy.country and country.upper() != policy.country:
        mismatches += 1
    status = 'FAIL' if mismatches else 'WARN' if missing or not devices else 'PASS'
    return real_verdict('C2', status, 'alinear SIM locale zona y geografia del proxy',
                        checked=len(rows), missing=missing, mismatches=mismatches,
                        proxy_verified=reused, proxy_skipped=skipped, **diagnostics)


async def evaluate_c4_real(devices, policy, ctx, proxy_manager):
    method = getattr(proxy_manager, 'contar_salidas_distintas', None)
    if method is None:
        return real_verdict('C4', 'WARN', 'habilitar consulta agregada del pool', missing=1,
                            **diagnostic_defaults('C4', {}))
    samples = min(32, max(C4_MUESTRAS_MINIMAS, policy.stage, policy.proxy_min_distinct_exit_ips))
    try:
        result = await asyncio.wait_for(method(muestras=samples, timeout=C4_TIMEOUT_SEGUNDOS),
                                        timeout=C4_TIMEOUT_GLOBAL_SEGUNDOS)
        if (not isinstance(result, dict) or any(type(result.get(k)) is not int or result[k] < 0
                for k in ('distinct', 'total', 'errors', 'timeouts'))
                or result['distinct'] > result['total'] or result['total'] > samples
                or result['errors'] + result['timeouts'] > result['total']):
            raise ValueError()
    except Exception:
        return real_verdict('C4', 'WARN', 'comprobar disponibilidad del pool', missing=1,
                            **diagnostic_defaults('C4', {}))
    insufficient = result['distinct'] < policy.proxy_min_distinct_exit_ips
    ttl_bad = 0 < policy.proxy_sticky_ttl < policy.stage * policy.hold_max
    status = 'FAIL' if insufficient else 'WARN' if result['errors'] or result['timeouts'] or ttl_bad or result['total'] < samples else 'PASS'
    return real_verdict('C4', status, 'revisar salidas rotacion y TTL contratado',
                        **result, ttl_incompatible=int(ttl_bad),
                        **c4_diagnostics(result, ctx.get('c4_attempt_details')))


async def evaluate_c5_real(devices, policy, ctx, db):
    try:
        rows = db.execute('''SELECT m.captcha_count, m.softblock_count, m.logout_count
            FROM farm_stage_metrics m JOIN farm_preflight_runs r ON r.run_id=m.run_id
            WHERE m.stage=? AND r.stage=? AND r.synthetic=0 AND r.finished_at IS NOT NULL
            AND r.decision IN ('proceed','proceed_with_warnings','abort')
            AND EXISTS (SELECT 1 FROM farm_preflight_verdicts v WHERE v.run_id=r.run_id AND v."constraint"='C5')''',
            (policy.stage, policy.stage)).fetchall()
        if any(any(value is not None and (type(value) is not int or value < 0) for value in row) for row in rows):
            raise ValueError()
        complete = [row for row in rows if all(value is not None for value in row)]
        # Missing observations cannot earn PASS or hide an observed incident.
        totals = [sum(row[index] for row in rows if row[index] is not None) for index in range(3)]
        exceeded = any(total > maximum for total, maximum in zip(totals,
                      (policy.max_captchas, policy.max_softblocks, policy.max_logouts)))
        status = 'FAIL' if exceeded else 'WARN' if len(complete) < policy.min_metric_samples else 'PASS'
        return real_verdict('C5', status, 'recoger metricas reales suficientes de la etapa',
            samples=len(complete), captcha_count=totals[0], softblock_count=totals[1], logout_count=totals[2])
    except Exception:
        return real_verdict('C5', 'WARN', 'verificar historial de metricas de la etapa', missing=1)


async def build_real_context(policy, proxy_manager, run_id, proxy_verified, selected_plates=None):
    """Read existing ADB servers only. No reconnect, database, launch or gesture."""
    from core.adb_pool import ADBServer, DeviceRoute, descubrir_pool
    from config.proxies import adb
    selected = {}
    excluded = set()
    requested = None
    if selected_plates is not None:
        if not isinstance(selected_plates, list) or len(selected_plates) != policy.stage:
            raise ValueError('Seleccion de placas invalida')
        requested = {}
        ids, refs, map_plates = set(), set(), set()
        routes = set()
        for item in selected_plates:
            if (not isinstance(item, dict) or not isinstance(item.get('serial'), str)
                    or not re.fullmatch('[0-9a-f]{16}', item.get('device_ref', ''))
                    or not re.fullmatch('p[0-9]{2}', item.get('map_plate', ''))
                    or not isinstance(item.get('server'), str) or not item['server']
                    or not isinstance(item.get('transporte'), str)
                    or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{3,100}', item['transporte'])
                    or not isinstance(item.get('panda_id'), str)):
                raise ValueError('Seleccion de placas invalida')
            if (item['serial'] in requested or item['panda_id'] in ids
                    or item['device_ref'] in refs or item['map_plate'] in map_plates
                    or (item['server'], item['transporte']) in routes):
                raise ValueError('Seleccion de placas duplicada')
            requested[item['serial']] = item
            routes.add((item['server'], item['transporte']))
            ids.add(item['panda_id']); refs.add(item['device_ref']); map_plates.add(item['map_plate'])
        if map_plates != {'p' + str(index).zfill(2) for index in range(1, policy.stage + 1)}:
            raise ValueError('Seleccion de placas incompleta')

    def read(route, *args):
        return adb('-H', route.server.host, '-P', str(route.server.port), '-s', route.serial,
                   'shell', *args, timeout=2)

    def properties(route):
        text = read(route, 'getprop')
        return dict(re.findall(r'^\[([^\]]+)\]: \[([^\]]*)\]$', text, re.MULTILINE))

    if requested is not None:
        for item in selected_plates:
            host, _, port = item['server'].rpartition(':')
            server = ADBServer(host.strip('[]'), int(port))
            if server.key != item['server']:
                raise ValueError('Servidor de seleccion invalido')
            route = DeviceRoute(item['transporte'], server, 'device')
            try:
                props = await asyncio.wait_for(asyncio.to_thread(properties, route), timeout=DEVICE_PROBE_TIMEOUT_SECONDS)
            except Exception:
                raise ValueError('Seleccion de placas incompleta') from None
            identities = {props.get(key) for key in ('ro.serialno', 'ro.boot.serialno')} - {None, ''}
            if identities != {item['serial']}:
                raise ValueError('Identidad fisica de seleccion invalida')
            selected[item['panda_id']] = (route, props)
    else:
        try:
            snapshot = await asyncio.wait_for(asyncio.to_thread(descubrir_pool, timeout=3), timeout=DISCOVERY_TIMEOUT_SECONDS)
            physicals = set()
            for route in snapshot.devices.values():
                if route.status != 'device':
                    continue
                try:
                    props = await asyncio.wait_for(asyncio.to_thread(properties, route), timeout=DEVICE_PROBE_TIMEOUT_SECONDS)
                except Exception:
                    continue
                physical = props.get('ro.serialno') or props.get('ro.boot.serialno')
                if physical and physical not in physicals:
                    physicals.add(physical)
                    selected['p'+str(len(selected)+1).zfill(2)] = (route, props)
                    if len(selected) == policy.stage:
                        break
        except Exception:
            pass

    async def integrity(device):
        route, props = selected[device]
        uid, packages = await asyncio.gather(asyncio.to_thread(read, route, 'id', '-u'),
                                           asyncio.to_thread(read, route, 'pm', 'list', 'packages'))
        qemu = props.get('ro.kernel.qemu')
        result = {'root_detected': uid.strip() == '0' if uid.strip().isdigit() else None,
                'emulator_detected': qemu == '1' if qemu in ('0', '1') else None,
                'automation_detected': any(name in packages.splitlines() for name in
                    ('package:io.appium.uiautomator2.server', 'package:io.appium.uiautomator2.server.test'))
                    if packages.startswith('package:') else None,
                'play_integrity': None}
        if requested is not None and any(result.get(key) is True for key in
                                         ('root_detected', 'emulator_detected', 'automation_detected')):
            excluded.add(device)
        return result

    async def identity(device):
        _, props = selected[device]
        result = {'sim_country': props.get('gsm.sim.operator.iso-country', ''),
                'locale': props.get('persist.sys.locale') or props.get('ro.product.locale', ''),
                'timezone': props.get('persist.sys.timezone', '')}
        if requested is not None:
            locale = re.search(r'[_-]([A-Za-z]{2})$', result['locale'])
            country = timezone_country(result['timezone'])
            if (not locale or not country or policy.country and
                    (locale[1].upper() != policy.country or country != policy.country)):
                excluded.add(device)
        return result

    return {'synthetic': False, 'real_connectors_ready': True, 'devices': list(selected), 'run_id': run_id,
            'integrity_probe': integrity, 'identity_probe': identity,
            'proxy_manager': proxy_manager, 'proxy_preflight_verified': proxy_verified,
            'excluded_devices': excluded,
            'c3': {key: {'hold_seconds': policy.hold_min} for key in selected}}


@dataclass(frozen=True)
class ConstraintVerdict:
    constraint: str
    status: str
    reason: str
    counters: dict

    def __post_init__(self):
        if (self.constraint not in ('C1', 'C2', 'C3', 'C4', 'C5')
                or self.status not in ('PASS', 'WARN', 'FAIL')
                or not isinstance(self.reason, str)
                or not re.fullmatch(self.constraint + r' [A-Z_]+ \| alternativa: [A-Za-z_ ]+', self.reason)
                or len(self.reason) > 200 or not self.reason.isascii()
                or not isinstance(self.counters, dict)
                or not valid_counters(self.constraint, self.counters)):
            raise ValueError('Veredicto sintetico invalido')


def valid_counters(constraint, counters):
    legacy = {
        'C1': {'checked', 'missing', 'failed', 'negative'},
        'C2': {'checked', 'missing', 'failed', 'mismatches'},
        'C3': {'checked', 'missing', 'failed'},
        'C4': {'checked', 'missing', 'failed', 'distinct', 'total', 'errors', 'timeouts', 'ttl_incompatible'},
        'C5': {'checked', 'missing', 'samples', 'captcha_count', 'softblock_count', 'logout_count'},
    }
    integer_keys = legacy[constraint] | set(C1_DIAGNOSTIC_KEYS if constraint == 'C1' else
        C2_DIAGNOSTIC_KEYS if constraint == 'C2' else ('attempts',) if constraint == 'C4' else ())
    boolean_keys = {'proxy_verified', 'proxy_skipped'} if constraint == 'C2' else {'data_available'} if constraint == 'C4' else set()
    for key, value in counters.items():
        if not isinstance(key, str) or not re.fullmatch('[a-z_]+', key):
            return False
        if key in integer_keys:
            if type(value) is not int or value < 0:
                return False
        elif key in boolean_keys:
            if type(value) is not bool:
                return False
        elif constraint == 'C4' and key == 'errors_by_kind':
            if (not isinstance(value, dict) or set(value) != set(C4_ERROR_KINDS)
                    or any(type(item) is not int or item < 0 for item in value.values())):
                return False
        elif constraint == 'C4' and key in ('distinct_per_attempt', 'latency_ms_by_attempt'):
            item_type = bool if key == 'distinct_per_attempt' else int
            if (not isinstance(value, list) or len(value) > 32
                    or any(type(item) is not item_type or item_type is int and item < 0 for item in value)):
                return False
        else:
            return False
    if counters.get('proxy_verified') is True and counters.get('proxy_skipped') is True:
        return False
    if constraint == 'C4' and 'attempts' in counters and counters['attempts'] != counters.get('total'):
        return False
    if counters.get('data_available') is True:
        required = {'attempts', 'total', 'distinct', 'errors', 'timeouts', 'errors_by_kind',
                    'distinct_per_attempt', 'latency_ms_by_attempt'}
        if not required <= set(counters):
            return False
        if (len(counters['distinct_per_attempt']) != counters['attempts']
                or len(counters['latency_ms_by_attempt']) != counters['attempts']
                or sum(counters['distinct_per_attempt']) != counters['distinct']
                or sum(counters['errors_by_kind'].values()) != counters['errors']
                or counters['distinct'] + counters['errors'] + counters['timeouts'] > counters['total']):
            return False
    return True


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
        columns = {row[1] for row in db.execute('PRAGMA table_info(farm_preflight_runs)')}
        if 'synthetic' not in columns:
            db.execute('ALTER TABLE farm_preflight_runs ADD COLUMN synthetic INT NOT NULL DEFAULT 1')


def now():
    return datetime.now(timezone.utc).isoformat()


def record_native_metrics(db, run_id, stage, completed=True):
    """Persist one uninspected native-run sample; missing incidents remain NULL."""
    if not completed:
        return False
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', run_id) or type(stage) is not int:
        raise ValueError('Metricas de corrida invalidas')
    with db:
        db.execute('''INSERT INTO farm_stage_metrics
            (run_id,stage,captcha_count,softblock_count,logout_count,recorded_at)
            VALUES (?,?,NULL,NULL,NULL,?)''', (run_id, stage, now()))
    return True


async def run_farm_preflight(devices, policy, ctx, db):
    run_id = ctx.get('run_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', run_id):
        raise ValueError('Fixture sintetico invalido')
    synthetic = ctx.get('synthetic') is True
    if not synthetic and not ctx.get('real_connectors_ready'):
        raise ValueError('Conectores reales no disponibles')
    migrate(db)
    with db:
        db.execute('INSERT INTO farm_preflight_runs (id,run_id,stage,started_at,finished_at,decision,synthetic) VALUES (?, ?, ?, ?, NULL, NULL, ?)',
                   (run_id, run_id, policy.stage, now(), int(synthetic)))
    verdicts = []
    try:
        evaluators = (evaluate_c1, evaluate_c2, evaluate_c3, evaluate_c4, evaluate_c5)
        if not synthetic:
            async def c2(devices, policy, ctx):
                return await evaluate_c2_real(devices, policy, ctx, ctx.get('proxy_manager'))
            async def c3(devices, policy, ctx):
                names = ['p' + str(index).zfill(2) for index in range(1, len(devices) + 1)]
                planned = {name: ctx.get('c3', {}).get(device) for name, device in zip(names, devices)}
                return await evaluate_c3(names, policy, {**ctx, 'synthetic': True, 'c3': planned})
            async def c4(devices, policy, ctx):
                return await evaluate_c4_real(devices, policy, ctx, ctx.get('proxy_manager'))
            async def c5(devices, policy, ctx):
                return await evaluate_c5_real(devices, policy, ctx, db)
            evaluators = (evaluate_c1_real, c2, c3, c4, c5)
        for evaluate in evaluators:
            await asyncio.sleep(0)
            item = await evaluate(devices, policy, ctx)
            verdicts.append(item)
            with db:
                db.execute('INSERT INTO farm_preflight_verdicts (run_id, "constraint", status, reason, counters_json) VALUES (?, ?, ?, ?, ?)',
                    (run_id, item.constraint, item.status, item.reason, json.dumps(item.counters, ensure_ascii=True)))
        decision = decide(verdicts, policy)
        with db:
            if synthetic:
                _, totals = metrics(devices, ctx)
                db.execute('INSERT INTO farm_stage_metrics (run_id, stage, captcha_count, softblock_count, logout_count, recorded_at) VALUES (?, ?, ?, ?, ?, ?)',
                    (run_id, policy.stage, totals['captcha_count'], totals['softblock_count'], totals['logout_count'], now()))
            db.execute('UPDATE farm_preflight_runs SET finished_at=?, decision=? WHERE id=?', (now(), decision, run_id))
        return verdicts
    except (KeyboardInterrupt, asyncio.CancelledError):
        with db:
            db.execute('DELETE FROM farm_preflight_verdicts WHERE run_id=?', (run_id,))
            db.execute('UPDATE farm_preflight_runs SET finished_at=?, decision=? WHERE id=?', (now(), 'cancelled', run_id))
        raise


def write_evidence(root, run_id, policy, verdicts, code, cancelled=False, ctx=None):
    synthetic = ctx is None or ctx.get('synthetic') is True
    serialized = []
    diagnostic_available = {}
    for item in ([] if cancelled else verdicts):
        defaults = diagnostic_defaults(item.constraint, item.counters)
        enriched = {**defaults, **item.counters}
        checked = ConstraintVerdict(item.constraint, item.status, item.reason, enriched)
        serialized.append(asdict(checked))
        if defaults:
            diagnostic_available[item.constraint] = set(defaults) <= set(item.counters)
    report = {'timestamp': now(), 'run_id': run_id, 'synthetic': synthetic,
              'policy': asdict(policy) if policy else None,
              'decision': 'cancelled' if cancelled else decide(verdicts, policy) if verdicts else 'precheck_failed',
              'cancelled': cancelled, 'verdicts': serialized,
              'diagnostic_fields_available': diagnostic_available,
              'exit_code': code, 'warnings': ['Preflight evidence does not authorize stage execution.']}
    if not synthetic:
        names = ('evaluate_c1_real', 'evaluate_c2_real', 'evaluate_c3', 'evaluate_c4_real', 'evaluate_c5_real')
        report['adapters'] = {name: {'status': item.status} for name, item in zip(names, verdicts)}
        report['metrics_origin'] = 'existing_real_history_only'
        report['c3_origin'] = 'planned_configuration'
    path = root / 'runs' / ('farm_preflight_' + run_id + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='ascii')
    return path
