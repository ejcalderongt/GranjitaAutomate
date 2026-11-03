"""Admisión WAL de OpenAI para workers async; comparte cuotas con workers sync."""
import asyncio
import time
from types import SimpleNamespace

from core.runtime_health import liberar_api


class AsyncClienteRecuperable:
    def __init__(self, client, db, token, run_id, stop, rpm, concurrency, heartbeat):
        self.client, self.db, self.token = client, db, token
        self.run_id, self.stop = run_id, stop
        self.rpm, self.concurrency, self.heartbeat = rpm, concurrency, heartbeat
        self.last_api_latency_ms = self.last_admission_latency_ms = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def _admit(self):
        now = time.time()
        with self.db.conexion() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('DELETE FROM api_slots WHERE expires<?', (now,))
            count = con.execute('SELECT COUNT(*) FROM api_slots').fetchone()[0]
            row = con.execute('SELECT next_start FROM api_rate WHERE run_id=?', (self.run_id,)).fetchone()
            if count >= self.concurrency or (row and row['next_start'] > now):
                return False
            con.execute('INSERT INTO api_slots VALUES (?,?,?)', (self.token, self.run_id, now+120))
            con.execute('INSERT INTO api_rate VALUES (?,?) ON CONFLICT(run_id) DO UPDATE SET next_start=excluded.next_start',
                        (self.run_id, now+60/self.rpm))
            return True

    async def create(self, **kwargs):
        acquired = False
        heartbeat = 0
        started = time.perf_counter()
        self.last_api_latency_ms = self.last_admission_latency_ms = None
        try:
            while not self.stop.is_set():
                admission = asyncio.create_task(asyncio.to_thread(self._admit))
                try:
                    acquired = await asyncio.shield(admission)
                except asyncio.CancelledError:
                    acquired = await admission
                    raise
                if acquired:
                    if self.stop.is_set():
                        raise InterruptedError('Consulta IA cancelada')
                    network_started = time.perf_counter()
                    self.last_admission_latency_ms = (network_started-started)*1000
                    try:
                        return await self.client.chat.completions.create(**kwargs)
                    finally:
                        self.last_api_latency_ms = (time.perf_counter()-network_started)*1000
                if time.monotonic()-heartbeat > 5:
                    await self.heartbeat()
                    heartbeat = time.monotonic()
                await asyncio.sleep(.25)
            raise InterruptedError('Consulta IA cancelada')
        finally:
            if acquired:
                release = asyncio.create_task(asyncio.to_thread(liberar_api, self.db, self.token))
                try:
                    await asyncio.shield(release)
                except asyncio.CancelledError:
                    await release
                    raise
