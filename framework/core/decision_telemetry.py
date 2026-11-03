"""Histórico JSONL local por cuenta y ejecución, sin credenciales de infraestructura."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()


class DecisionTelemetry:
    def __init__(self, account_id, run_id=None, *, root=None):
        from core.browser import validar_account_id, directorio_cuenta
        validar_account_id(account_id)
        self.account_id = account_id
        self.run_id = validar_account_id(run_id or uuid4().hex)
        folder = directorio_cuenta(Path(root or ROOT/'logs'), account_id)
        self.path = folder / ('decisiones-' + self.run_id + '.jsonl')

    def append(self, event, *, cycle_id, **payload):
        row = {'schema_version': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
               'run_id': self.run_id, 'account_id': self.account_id,
               'cycle_id': cycle_id, 'event': event, **payload}
        line = (json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        if len(line) > 64000:
            raise ValueError('Evento de telemetría demasiado grande')
        with _LOCK:
            with self.path.open('ab') as file:
                file.write(line)
                file.flush()
                os.fsync(file.fileno())


def resumir_decisiones(path):
    """Contar recomendaciones; no confundirlas con acciones aceptadas por TikTok."""
    decisions, comments, latencies = [], Counter(), []
    errors = malformed = fallbacks = 0
    with Path(path).open(encoding='utf-8') as file:
        for line in file:
            try:
                event = json.loads(line)
            except ValueError:
                malformed += 1
                continue
            if event.get('event') == 'ai_error':
                errors += 1
            if event.get('event') != 'decision':
                continue
            decision = event['decision']
            fallbacks += event.get('decision_origin') == 'fallback'
            decisions.append(decision)
            if decision.get('comentar'):
                comments[decision.get('comentario', '')] += 1
            latencies.append(event['latency_ms'])
    return {'decisiones': len(decisions), 'errores_ia': errors, 'fallbacks': fallbacks, 'lineas_invalidas': malformed,
            'likes_recomendados': sum(d.get('dar_like', False) for d in decisions),
            'comentarios_recomendados': sum(comments.values()),
            'compartidos_recomendados': sum(d.get('compartir', False) for d in decisions),
            'comentarios_repetidos': {text: count for text, count in comments.items() if count > 1},
            'latencia_media_ms': round(sum(latencies)/len(latencies), 2) if latencies else None,
            'alcance': 'recomendaciones; no confirma acciones en el servidor'}
