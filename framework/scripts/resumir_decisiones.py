"""Resumir un histórico JSONL de decisiones sin iniciar navegador ni llamar a OpenAI."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.decision_telemetry import resumir_decisiones


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('historial', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(resumir_decisiones(args.historial), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('No se pudo resumir el histórico: ' + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
