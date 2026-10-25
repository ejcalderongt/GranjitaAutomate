"""Lectura del total de likes sin inicializar ni recuperar la cola de tareas."""
import sqlite3
from pathlib import Path
from .core import DATA


def verified_like_count(path=None):
    path=Path(path) if path else DATA/'automation.sqlite3'
    if not path.exists():return 0
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='like_events'").fetchone():return 0
        return db.execute('''WITH latest AS (
            SELECT task_id,COALESCE(json_extract(data,'$.target'),'lab_like_01') AS target,MAX(id) AS id
            FROM like_events WHERE kind='verified'
            GROUP BY task_id,COALESCE(json_extract(data,'$.target'),'lab_like_01'))
            SELECT COUNT(*) FROM latest l JOIN like_events e ON e.id=l.id
            JOIN tasks t ON t.id=l.task_id
            WHERE t.action IN ('lab_like','lab_like_flow') AND json_extract(e.data,'$.outcome')='applied' ''').fetchone()[0]
    finally:db.close()
