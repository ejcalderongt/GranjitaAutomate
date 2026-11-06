"""Keep implicit decision journals inside each test's temporary directory."""
from pathlib import Path

import pytest
from tests._base_guard import install; install()


PROJECT_LOGS = Path(__file__).resolve().parents[1] / 'logs'


def _log_files(folder):
    return {path.relative_to(folder) for path in folder.rglob('*') if path.is_file()}


def _assert_no_new_log_files(folder, before):
    if _log_files(folder) - before:
        raise AssertionError('Suite created files in project logs; use tmp_path')


@pytest.fixture(scope='session', autouse=True)
def _guard_project_logs():
    before = _log_files(PROJECT_LOGS)
    yield
    _assert_no_new_log_files(PROJECT_LOGS, before)


@pytest.fixture(autouse=True)
def _isolate_default_decision_telemetry(tmp_path, monkeypatch):
    from core import decision_telemetry
    # The constructor reads its defining module's ROOT at call time. This also
    # covers classes imported by other modules without changing explicit roots.
    monkeypatch.setattr(decision_telemetry, 'ROOT', tmp_path)


@pytest.fixture(scope='session', autouse=True)
def _protect_real_databases_during_diagnostic():
    from tests._base_guard import protect_real_bases
    with protect_real_bases():
        yield
