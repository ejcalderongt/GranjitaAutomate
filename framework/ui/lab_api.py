"""Loopback laboratory panel: sanitized evidence and synthetic checks only."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from config.farm_policy import FarmPolicy
from config.farm_preflight import load_synthetic_fixture, run_farm_preflight, write_evidence
from core.device_aliases import read_aliases
from core.panda_lab_status import read_dashboard

ROOT = Path(__file__).resolve().parents[1]
SAFE_NAME = re.compile(r'farm_preflight_[A-Za-z0-9_-]{1,100}\.json')


def safe_evidence(path):
    if path.is_symlink() or not SAFE_NAME.fullmatch(path.name) or path.stat().st_size > 1_000_000:
        raise ValueError('Evidence not available')
    raw = json.loads(path.read_text(encoding='ascii'))
    if not isinstance(raw, dict) or not isinstance(raw.get('verdicts', []), list):
        raise ValueError('Invalid evidence object')
    decision = raw.get('decision')
    if decision not in ('proceed', 'proceed_with_warnings', 'abort', 'cancelled', 'precheck_failed'):
        raise ValueError('Invalid evidence')
    verdicts = []
    for row in raw.get('verdicts', []):
        if not isinstance(row, dict) or not isinstance(row.get('counters', {}), dict):
            raise ValueError('Invalid verdict object')
        if row.get('constraint') not in ('C1', 'C2', 'C3', 'C4', 'C5') or row.get('status') not in ('PASS', 'WARN', 'FAIL'):
            raise ValueError('Invalid verdict')
        counters = {k: v for k, v in row.get('counters', {}).items()
                    if re.fullmatch('[a-z_]+', k) and type(v) in (int, bool) and v >= 0}
        verdicts.append({'constraint': row['constraint'], 'status': row['status'], 'counters': counters})
    return {'id': path.name, 'synthetic': raw.get('synthetic') is True,
            'decision': decision, 'verdicts': verdicts}


def create_app(root=ROOT, checker=None):
    root = Path(root).resolve()
    state = {'status': 'idle', 'reason': 'Ready for synthetic checks', 'last_check': None}
    task = None

    async def synthetic_check():
        fixture = load_synthetic_fixture(ROOT / 'tests/fixtures/farm_stage3.json')
        fixture['run_id'] = 'ui-synthetic-' + uuid4().hex
        with sqlite3.connect(':memory:') as db:
            verdicts = await run_farm_preflight(fixture['devices'], FarmPolicy(), fixture, db)
        path = write_evidence(root, fixture['run_id'], FarmPolicy(), verdicts, 0, ctx=fixture)
        return safe_evidence(path)

    async def work():
        try:
            state['last_check'] = await (checker or synthetic_check)()
            state.update(status='completed', reason='Synthetic check completed')
        except asyncio.CancelledError:
            state.update(status='cancelled', reason='Stopped cooperatively')
        except Exception:
            state.update(status='failed', reason='Synthetic check failed')

    @asynccontextmanager
    async def lifespan(app):
        yield
        if task and not task.done():
            task.cancel()
            await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        from fastapi.responses import JSONResponse
        if request.url.hostname not in ('localhost', '127.0.0.1', '::1'):
            return JSONResponse({'detail': 'Loopback host required'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Origin not authorized'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        return response

    def evidence_path(name):
        if not SAFE_NAME.fullmatch(name):
            raise HTTPException(404, 'Evidence not found')
        path = root / 'runs' / name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Evidence not found')
        return path

    @app.get('/api/status')
    async def status():
        latest = None
        paths = sorted((root / 'runs').glob('farm_preflight_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths:
            try:
                latest = safe_evidence(path)
                break
            except (ValueError, OSError):
                continue
        try:
            inventory = await asyncio.to_thread(read_aliases, root)
            inventory_status = 'registered' if inventory else 'empty'
        except (OSError, ValueError, KeyError, sqlite3.Error):
            inventory, inventory_status = [], 'unavailable'
        dashboard = await asyncio.to_thread(read_dashboard, root, inventory)
        return {**state, 'stages': {'IA': 'prepared', 'UI': 'local_only', 'E2': 'pending_live_validation'},
                'last_preflight': latest, 'last_run': None,
                'inventory': inventory, 'inventory_status': inventory_status,
                'dashboard': dashboard,
                'allowed_actions': ['verify', 'stop'], 'real_execution_authorized': False}

    @app.get('/api/evidence')
    async def evidence_list():
        result = []
        for path in sorted((root / 'runs').glob('farm_preflight_*.json'), reverse=True):
            try:
                result.append(safe_evidence(path))
            except (ValueError, OSError):
                continue
            if len(result) == 100:
                break
        return result

    @app.get('/api/evidence/{name}')
    async def evidence(name: str):
        try:
            return safe_evidence(evidence_path(name))
        except (ValueError, OSError):
            raise HTTPException(404, 'Evidence not available') from None

    @app.post('/api/actions/{action}')
    async def action(action: str, request: Request):
        nonlocal task
        if request.headers.get('X-Lab-Action') != 'synthetic' or action not in ('verify', 'stop'):
            raise HTTPException(403, 'Action not authorized')
        if action == 'stop':
            if task and not task.done():
                task.cancel()
                await task
            return {'status': state['status']}
        if task and not task.done():
            raise HTTPException(409, 'A check is already running')
        state.update(status='running', reason='Synthetic checks only')
        task = asyncio.create_task(work())
        return {'status': 'running'}

    @app.get('/')
    async def index():
        return FileResponse(Path(__file__).parent / 'lab_static/index.html')

    @app.get('/static/{name}')
    async def static(name: str):
        if name not in ('app.js', 'style.css'):
            raise HTTPException(404)
        return FileResponse(Path(__file__).parent / 'lab_static' / name)

    return app


app = create_app()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765, access_log=False)
