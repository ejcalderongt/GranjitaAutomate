"""Consultar Panda sin modificar nombres, grupos ni configuración."""
from collections import Counter
import json
from granjita.core import DATA,now
from granjita.panda_api import list_devices


def main():
    rows=list_devices()
    DATA.mkdir(exist_ok=True)
    (DATA/'panda-inventory.json').write_text(json.dumps(dict(at=now(),devices=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Registros API:',len(rows))
    print('Estados:',dict(Counter(str(r.get('status','no informado')) for r in rows)))
    print('Modos:',dict(Counter(str(r.get('mode','no informado')) for r in rows)))
    print('Con onlySerial:',sum(bool(r.get('onlySerial')) for r in rows))


if __name__=='__main__':
    main()
