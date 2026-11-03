"""Explicit policy for synthetic farm checks; no device admission is implied."""
from dataclasses import dataclass
import math
import os
from types import MappingProxyType

from core.project_env import load_project_environment

EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_FARM_ABORT_FAIL = 2
EXIT_FARM_ABORT_WARN = 3
EXIT_FARM_ABORT_PRECHECK = 4
EXIT_MESSAGES = MappingProxyType({
    0: 'Lote finalizado sin abortos de politica de granja',
    1: 'Configuracion invalida: revisa las variables PANDA_POLICY_* y vuelve a intentar',
    2: 'Lote abortado por constraint en FAIL: revisa las razones mostradas y corrige antes de reintentar',
    3: 'Lote abortado por constraint en WARN con ABORT_ON_WARN activo: desactiva esa bandera o corrige el WARN',
    4: 'Lote abortado antes de tocar Panda o Android por preflight fallido: revisa el preflight de proxy y de granja',
})
POLICY_VARIABLES = (
    'PANDA_POLICY_STAGE', 'PANDA_POLICY_HOLD_MIN', 'PANDA_POLICY_HOLD_MAX',
    'PANDA_POLICY_ABORT_ON_FAIL', 'PANDA_POLICY_ABORT_ON_WARN', 'PANDA_POLICY_COUNTRY',
)


@dataclass(frozen=True)
class FarmPolicy:
    stage: int = 3
    hold_min: float = 8
    hold_max: float = 22
    abort_on_fail: bool = True
    abort_on_warn: bool = False
    country: str = ''

    def __post_init__(self):
        if (type(self.stage) is not int or self.stage not in (3, 10, 34)
                or type(self.abort_on_fail) is not bool or type(self.abort_on_warn) is not bool
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in (self.hold_min, self.hold_max))
                or not 8 <= self.hold_min < self.hold_max <= 22
                or not isinstance(self.country, str)
                or self.country and (len(self.country) != 2 or not self.country.isascii()
                                     or not self.country.isalpha() or not self.country.isupper())):
            raise ValueError('Politica de granja invalida')


def load_farm_policy(path=None):
    load_project_environment(path)
    def boolean(name, default):
        value = os.getenv(name, default).lower()
        if value not in ('true', 'false', '1', '0'):
            raise ValueError('Politica de granja invalida')
        return value in ('true', '1')
    try:
        return FarmPolicy(
            stage=int(os.getenv('PANDA_POLICY_STAGE', '3')),
            hold_min=float(os.getenv('PANDA_POLICY_HOLD_MIN', '8')),
            hold_max=float(os.getenv('PANDA_POLICY_HOLD_MAX', '22')),
            abort_on_fail=boolean('PANDA_POLICY_ABORT_ON_FAIL', 'true'),
            abort_on_warn=boolean('PANDA_POLICY_ABORT_ON_WARN', 'false'),
            country=os.getenv('PANDA_POLICY_COUNTRY', '').upper(),
        )
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Politica de granja invalida') from None


def stage_limits(policy):
    return {'stage': policy.stage, 'device_limit': policy.stage,
            'hold_min': policy.hold_min, 'hold_max': policy.hold_max,
            'abort_on_fail': policy.abort_on_fail, 'abort_on_warn': policy.abort_on_warn}
