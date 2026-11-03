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
    'PANDA_POLICY_PROXY_MIN_DISTINCT_EXIT_IPS', 'PANDA_POLICY_PROXY_STICKY_TTL',
    'PANDA_POLICY_MAX_CAPTCHAS', 'PANDA_POLICY_MAX_SOFTBLOCKS',
    'PANDA_POLICY_MAX_LOGOUTS', 'PANDA_POLICY_MIN_METRIC_SAMPLES',
)


@dataclass(frozen=True)
class FarmPolicy:
    stage: int = 3
    hold_min: float = 8
    hold_max: float = 22
    abort_on_fail: bool = True
    abort_on_warn: bool = False
    country: str = ''
    proxy_min_distinct_exit_ips: int = 3
    proxy_sticky_ttl: int = 0
    max_captchas: int = 0
    max_softblocks: int = 0
    max_logouts: int = 0
    min_metric_samples: int = 1

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
        for value, minimum, maximum in (
                (self.proxy_min_distinct_exit_ips, 1, 32), (self.proxy_sticky_ttl, 0, 86400),
                (self.max_captchas, 0, 1000000), (self.max_softblocks, 0, 1000000),
                (self.max_logouts, 0, 1000000), (self.min_metric_samples, 1, 1000000)):
            if type(value) is not int or not minimum <= value <= maximum:
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
            proxy_min_distinct_exit_ips=int(os.getenv('PANDA_POLICY_PROXY_MIN_DISTINCT_EXIT_IPS', '3')),
            proxy_sticky_ttl=int(os.getenv('PANDA_POLICY_PROXY_STICKY_TTL', '0')),
            max_captchas=int(os.getenv('PANDA_POLICY_MAX_CAPTCHAS', '0')),
            max_softblocks=int(os.getenv('PANDA_POLICY_MAX_SOFTBLOCKS', '0')),
            max_logouts=int(os.getenv('PANDA_POLICY_MAX_LOGOUTS', '0')),
            min_metric_samples=int(os.getenv('PANDA_POLICY_MIN_METRIC_SAMPLES', '1')),
        )
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Politica de granja invalida') from None


def stage_limits(policy):
    return {'stage': policy.stage, 'device_limit': policy.stage,
            'hold_min': policy.hold_min, 'hold_max': policy.hold_max,
            'abort_on_fail': policy.abort_on_fail, 'abort_on_warn': policy.abort_on_warn}
