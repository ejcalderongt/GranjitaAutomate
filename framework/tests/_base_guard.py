"""Test-only SQLite guard, inherited bootstrap and process-safe access journal."""
from contextlib import contextmanager
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = frozenset(os.path.normcase(str((ROOT / name).resolve())) for name in
    ('data/granja_tiktok.db', 'sessions/telemetry_qa.db'))
_installed = None
_thread_lock = threading.RLock()


def _destination(value, uri):
    try:
        value = os.fsdecode(os.fspath(value))
    except TypeError:
        return None, 'unknown'
    if value == ':memory:':
        return None, 'memory'
    mode = 'default'
    if uri and value.startswith('file:'):
        parsed = urlsplit(value)
        mode = parse_qs(parsed.query).get('mode', ['default'])[0]
        value = unquote(parsed.path)
        if parsed.netloc:
            value = '//' + parsed.netloc + value
        if len(value) > 2 and value[0] == '/' and value[2] == ':':
            value = value[1:]
    return os.path.normcase(str(Path(value).resolve())), mode


def configure_bootstrap(environment=None):
    """Configure only test entrypoints; ordinary application imports stay inert."""
    environment = os.environ if environment is None else environment
    mode = environment.setdefault('PANDA_BASE_GUARD_MODE', 'block')
    if mode not in ('block', 'observe'):
        raise RuntimeError('Modo de diagnostico invalido')
    folder = ROOT / 'runs/_guard_sitecustomize'
    folder.mkdir(parents=True, exist_ok=True)
    source = ('import os, sys\n'
              "if os.environ.get('PANDA_BASE_GUARD_MODE') in ('block', 'observe'):\n"
              '    sys.path.insert(0, ' + repr(str(ROOT)) + ')\n'
              '    from tests._base_guard import install\n'
              '    install()\n')
    target = folder / 'sitecustomize.py'
    if not target.exists() or target.read_text(encoding='ascii') != source:
        temporary = folder / ('sitecustomize.' + str(os.getpid()) + '.tmp')
        temporary.write_text(source, encoding='ascii')
        os.replace(temporary, target)
    paths = environment.get('PYTHONPATH', '').split(os.pathsep)
    environment['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(
        [str(folder), str(ROOT)] + [p for p in paths if p]))
    if not environment.get('PANDA_GUARD_ACCESS_FILE'):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        environment['PANDA_GUARD_ACCESS_FILE'] = str(ROOT / 'runs' /
            ('base_guard_access_' + stamp + '.json'))
    output = Path(environment['PANDA_GUARD_ACCESS_FILE']).resolve()
    if output.parent != (ROOT / 'runs').resolve():
        raise RuntimeError('Guard journal must stay inside project runs')
    try:
        with output.open('x', encoding='ascii') as file:
            file.write('[]')
    except FileExistsError:
        pass
    return output


def _append(output, row):
    """Serialize parent/child journal updates without using SQLite."""
    with _thread_lock, Path(str(output) + '.lock').open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            rows = json.loads(output.read_text(encoding='ascii'))
            rows.append(row)
            temporary = Path(str(output) + '.' + str(os.getpid()) + '.tmp')
            temporary.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding='ascii')
            os.replace(temporary, output)
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _callers():
    name = os.getenv('PYTEST_CURRENT_TEST', '').split(' (')[0]
    frames = []
    for item in inspect.stack(context=0)[2:]:
        path = Path(item.filename).resolve()
        if path == Path(__file__).resolve():
            continue
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        frames.append({'file': relative, 'function': item.function, 'line': item.lineno})
        if not name and relative.startswith('tests/') and item.function.startswith('test_'):
            name = relative + '::' + item.function
    return name or 'collection_or_child', frames[:16]


def install(mode=None, label='test'):
    global _installed
    if _installed is not None:
        return _installed
    if mode is not None:
        os.environ['PANDA_BASE_GUARD_MODE'] = mode
    output = configure_bootstrap()
    selected_mode = os.environ['PANDA_BASE_GUARD_MODE']
    original = sqlite3.connect

    def guarded(database, *args, **kwargs):
        uri = kwargs.get('uri', args[6] if len(args) > 6 else False)
        destination, access_mode = _destination(database, uri)
        if destination in PROTECTED:
            name, frames = _callers()
            blocked = selected_mode == 'block' and access_mode != 'ro'
            _append(output, {'test_name': name,
                'path': Path(destination).relative_to(ROOT).as_posix(), 'mode': access_mode,
                'action': 'blocked' if blocked else ('read_only_access' if access_mode == 'ro' else 'observed'),
                'blocked': blocked, 'caller_frame': frames[0] if frames else None,
                'stack': frames, 'pid': os.getpid(), 'runner': label})
            if blocked:
                raise RuntimeError('Base real protegida en modo test')
        return original(database, *args, **kwargs)

    sqlite3.connect = guarded
    sqlite3.dbapi2.connect = guarded
    _installed = {'path': output, 'mode': selected_mode}
    return _installed


@contextmanager
def protect_real_bases(mode=None, label='pytest'):
    yield install(mode=mode, label=label)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    install(label='unittest')
    from scripts.run_tests import run_isolated_unittest
    raise SystemExit(run_isolated_unittest(['-q', '--buffer']))
