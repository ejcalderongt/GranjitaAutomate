"""Offline, read-only promotion decisions. Never starts a device or network run."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3

STAGES = (3, 10, 34)


@dataclass(frozen=True)
class StageLimits:
    min_samples: int = 1

    def __post_init__(self):
        if type(self.min_samples) is not int or not 1 <= self.min_samples <= 10000:
            raise ValueError('Invalid stage limits')


@dataclass(frozen=True)
class StageDecision:
    stage: int
    decision: str
    next_stage: int | None
    reason: str
    samples: int


def load_stage_limits(path=None):
    if path is None:
        return {stage: StageLimits() for stage in STAGES}
    path = Path(path)
    if path.stat().st_size > 16384:
        raise ValueError('Stage limits too large')
    raw = json.loads(path.read_text(encoding='ascii'))
    if not isinstance(raw, dict) or set(raw) != {'3', '10', '34'}:
        raise ValueError('All three stages required')
    result = {}
    for stage in STAGES:
        values = raw[str(stage)]
        if not isinstance(values, dict) or set(values) != {'min_samples'}:
            raise ValueError('Unsupported stage limit')
        result[stage] = StageLimits(**values)
    return result


def evaluate_stage(db, stage, limits=None):
    if type(stage) is not int or stage not in STAGES:
        raise ValueError('Invalid stage')
    limits = limits or StageLimits()
    def blocked(reason, samples=0, abort=False):
        return StageDecision(stage, 'abort' if abort else 'blocked', None, reason, samples)
    try:
        run = db.execute('''SELECT run_id,decision FROM farm_preflight_runs
            WHERE stage=? AND synthetic=0 AND finished_at IS NOT NULL
            ORDER BY finished_at DESC, rowid DESC LIMIT 1''', (stage,)).fetchone()
        if run is None:
            return blocked('no_completed_physical_history')
        rows = db.execute('''SELECT captcha_count,softblock_count,logout_count
            FROM farm_stage_metrics WHERE stage=? AND run_id=?''', (stage, run[0])).fetchall()
        if any(any(v is not None and (type(v) is not int or v < 0) for v in row) for row in rows):
            return blocked('invalid_metrics')
        # An incident in even an incomplete sample prevents promotion.
        if any(any(v is not None and v > 0 for v in row) for row in rows):
            return blocked('observed_incident', len(rows), True)
        if run[1] not in ('proceed', 'proceed_with_warnings'):
            return blocked('previous_run_not_accepted')
        complete = [row for row in rows if all(v is not None for v in row)]
        if len(complete) != len(rows) or len(complete) < limits.min_samples:
            return blocked('incomplete_metrics', len(complete))
        c4 = db.execute('''SELECT status FROM farm_preflight_verdicts
            WHERE run_id=? AND "constraint"='C4' ORDER BY id DESC LIMIT 1''', (run[0],)).fetchone()
        if not c4 or c4[0] != 'PASS':
            return blocked('proxy_stage_not_accredited', len(complete))
        next_stage = STAGES[STAGES.index(stage) + 1] if stage != 34 else None
        return StageDecision(stage, 'promote' if next_stage else 'complete', next_stage,
                             'accepted_complete_metrics', len(complete))
    except sqlite3.Error:
        return blocked('history_schema_unavailable')


def stage_plan(database, stage, limits_path=None):
    limits = load_stage_limits(limits_path)
    path = Path(database).resolve()
    if not path.is_file():
        result = StageDecision(stage, 'blocked', None, 'history_unavailable', 0)
    else:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            result = evaluate_stage(db, stage, limits[stage])
    return {**asdict(result), 'mode': 'offline_planning', 'executes_next_stage': False,
            'stage_limits': {str(k): asdict(v) for k, v in limits.items()},
            'required_distinct_exit_defaults': {'3': 1, '10': 3, '34': 5}}
