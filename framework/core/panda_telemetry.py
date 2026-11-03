"""Auditorías visuales privadas separadas de las tablas QA de métricas puras."""
import asyncio
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3


def _guardar(path,run_id,cycle,rows):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=5)) as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA busy_timeout=5000')
        with con:
            con.execute('''CREATE TABLE IF NOT EXISTS auditorias_panda (
                run_id TEXT NOT NULL,ciclo INTEGER NOT NULL,timestamp_utc TEXT NOT NULL,
                id_placa TEXT NOT NULL,resultado_auditoria_visual TEXT,estado_operativo TEXT NOT NULL,
                latencia_ms REAL,error_codigo TEXT,swipe_estado TEXT NOT NULL,
                PRIMARY KEY(run_id,ciclo,id_placa))''')
            columns={r[1] for r in con.execute('PRAGMA table_info(auditorias_panda)')}
            for name in ('serial','alias'):
                if name not in columns:
                    con.execute(f'ALTER TABLE auditorias_panda ADD COLUMN {name} TEXT')
            con.execute('''CREATE VIEW IF NOT EXISTS logs_panda_farm AS SELECT
                timestamp_utc AS timestamp,id_placa AS panda_id,serial,alias,
                resultado_auditoria_visual AS analisis_vision,run_id,ciclo,estado_operativo,
                latencia_ms,swipe_estado FROM auditorias_panda''')
            for row in rows:
                con.execute('''INSERT INTO auditorias_panda (run_id,ciclo,timestamp_utc,id_placa,
                    resultado_auditoria_visual,estado_operativo,latencia_ms,error_codigo,swipe_estado,serial,alias)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(run_id,ciclo,id_placa) DO UPDATE SET
                    timestamp_utc=excluded.timestamp_utc,resultado_auditoria_visual=excluded.resultado_auditoria_visual,
                    estado_operativo=excluded.estado_operativo,latencia_ms=excluded.latencia_ms,
                    error_codigo=excluded.error_codigo,swipe_estado=excluded.swipe_estado,
                    serial=COALESCE(excluded.serial,auditorias_panda.serial),
                    alias=COALESCE(excluded.alias,auditorias_panda.alias)''',
                    (run_id,cycle,datetime.now(timezone.utc).isoformat(timespec='microseconds'),row['id_placa'],
                     json.dumps(row.get('informe'),ensure_ascii=False) if row.get('informe') is not None else None,
                     row['estado'],row.get('latencia_ms'),row.get('error_codigo'),row.get('swipe_estado','no_enviado'),
                     row.get('serial'),row.get('alias')))


async def guardar_lote_async(path,run_id,cycle,rows):
    """Una transacción para el lote entero; errores impiden el swipe sin auditar."""
    task=asyncio.create_task(asyncio.to_thread(_guardar,path,run_id,cycle,rows))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
