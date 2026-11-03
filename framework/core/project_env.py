"""Carga de credenciales del proyecto, sin ejecutar ni expandir contenido de .env."""
import os
from pathlib import Path


def load_project_environment(path=None):
    path=Path(path or os.getenv('PANDA_ENV_FILE') or Path(__file__).resolve().parents[1]/'.env')
    if not path.is_file():
        return bool(os.getenv('OPENAI_API_KEY'))
    allowed={'OPENAI_API_KEY','GHOST_CURSOR_REPOSITORY','GHOST_CURSOR_AUTOCLONE','PANDA_PROXY_COUNTRY',
             'PANDA_DEVICE_SALT','PANDA_DEVICE_MAP_KEEP',
             'PANDA_POLICY_STAGE','PANDA_POLICY_HOLD_MIN','PANDA_POLICY_HOLD_MAX',
             'PANDA_POLICY_ABORT_ON_FAIL','PANDA_POLICY_ABORT_ON_WARN','PANDA_POLICY_COUNTRY',
             'PANDA_POLICY_PROXY_MIN_DISTINCT_EXIT_IPS','PANDA_POLICY_PROXY_STICKY_TTL',
             'PANDA_POLICY_MAX_CAPTCHAS','PANDA_POLICY_MAX_SOFTBLOCKS',
             'PANDA_POLICY_MAX_LOGOUTS','PANDA_POLICY_MIN_METRIC_SAMPLES'}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        name,separator,value=line.strip().partition('=')
        name=name.strip()
        if separator and name in allowed and not os.getenv(name):
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
                value=value[1:-1]
            if value and '\x00' not in value and not any(c.isspace() for c in value):
                os.environ[name]=value
    return bool(os.getenv('OPENAI_API_KEY'))
