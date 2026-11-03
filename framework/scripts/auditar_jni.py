"""Inventario reproducible de declaraciones JNI Java/Smali, sin descompilar APK."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def escanear(root):
    findings = []
    count = 0
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.suffix not in ('.java', '.smali'):
            continue
        count += 1
        text = path.read_text(encoding='utf-8', errors='replace')
        identity = re.search(r'\bpackage\s+([\w.]+)', text) if path.suffix == '.java' else re.search(r'\.class[^\n]*\sL([^;]+);', text)
        for number, line in enumerate(text.splitlines(), 1):
            if 'loadLibrary' in line or re.search(r'\bnative\b', line):
                findings.append({'file': str(path.resolve()), 'line': number,
                                 'declaration': line.strip(),
                                 'package_or_class': identity.group(1) if identity else None})
    return {'scan_root': str(Path(root).resolve()), 'source_files': count,
            'findings': findings, 'existing_jni_contract_found': bool(findings),
            'scope': 'source text only; no binary JNI verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'android/agx_vpn_helper')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/jni-contract-audit.json')
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error('La carpeta fuente o descompilada no existe')
    report = escanear(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
