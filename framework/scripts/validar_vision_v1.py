"""Audit Vision contracts on saved images and verified hardware; never sends gestures."""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from core.ocr_agent import InformeVisionQA
from core.project_env import load_project_environment
from core.vision_contract import VERSION, VisibleUIReport, configuration_digest, messages, validate_response, verdict

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'runs/vision_threshold_diagnostic_20261111T003258616452Z'
RUN = 'panda-masivo-0e8eb74634c949aab6dc02b5d6eb88fb'
FIELDS = ('captcha', 'softblock', 'logged_out')


class BaselineField(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confidence: float = Field(ge=0, le=1)
    visible_signals: list[str]


class BaselineDiagnostics(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    feed_visible: bool
    feed_confidence: float = Field(ge=0, le=1)
    captcha: BaselineField
    softblock: BaselineField
    logged_out: BaselineField


class Baseline(InformeVisionQA):
    diagnostics: BaselineDiagnostics


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2) + '\n', encoding='ascii')
    temporary.replace(path)


def known_cost(usage):
    if not usage:
        return None
    values = [usage.get(key) for key in ('prompt_tokens', 'completion_tokens')]
    cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
    if any(type(v) is not int or v < 0 for v in [*values, cached]) or cached > values[0]:
        return None
    return round(((values[0] - cached) * .15 + cached * .075 + values[1] * .60) / 1e6, 8)


async def inspect(client, directory, image, name, variant, *, phase, iteration=1):
    if not 1 <= iteration <= 3:
        raise ValueError('Branch iteration limit exceeded')
    target = directory / (name + '.json')
    if target.exists():
        raise ValueError('Existing evidence cannot be replaced')
    attempts = list(directory.glob(name.split('_i')[0] + '_i*.json'))
    if len(attempts) >= 3:
        raise ValueError('Branch iteration limit exceeded')
    encoded = base64.b64encode(image.read_bytes()).decode('ascii')
    if variant == 'baseline':
        previous = json.loads((SOURCE / 'p03_current.json').read_text(encoding='ascii'))
        prompt_messages = [
            {'role': 'system', 'content': previous['system_prompt']},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Devuelve el informe estructurado de esta pantalla.'},
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}},
            ]},
        ]
        schema = Baseline
    else:
        prompt_messages = messages(encoded, variant)
        schema = VisibleUIReport
    payload = dict(model='gpt-4o-mini', max_completion_tokens=1400, messages=prompt_messages,
                   response_format={'type': 'json_schema', 'json_schema': {
                       'name': 'vision_contract_audit', 'strict': True, 'schema': schema.model_json_schema()}})
    record = {'name': name, 'phase': phase, 'iteration': iteration, 'variant': variant,
              'contract_sha256': configuration_digest(),
              'image': str(image.relative_to(ROOT)), 'image_sha256': digest(image),
              'schema': schema.model_json_schema(), 'model': payload['model'],
              'prompt_messages': [{**m, 'content': m['content']} for m in prompt_messages[:-1]],
              'user_instruction': prompt_messages[-1]['content'][0]['text'],
              'max_completion_tokens': payload['max_completion_tokens'], 'state': 'started',
              'contract_valid': False, 'cost_confirmed': False}
    save(target, record)
    started = time.monotonic()
    try:
        response = await client.chat.completions.create(**payload)
        raw = response.model_dump(mode='json')
        record.update(raw_response=raw, raw_text=response.choices[0].message.content,
                      usage=raw.get('usage'), state='received')
        record['estimated_usd'] = known_cost(record['usage'])
        record['cost_confirmed'] = record['estimated_usd'] is not None
        save(target, record)  # Persist usage before validation can fail.
        if variant == 'baseline':
            if response.choices[0].finish_reason != 'stop' or response.choices[0].message.refusal:
                raise ValueError('Baseline incomplete or refused')
            parsed = Baseline.model_validate_json(record['raw_text']).model_dump()
            confidence = {f: parsed['diagnostics'][f]['confidence'] for f in FIELDS}
            valid = all(type(parsed[f]) is bool and confidence[f] > 0 for f in FIELDS)
            record.update(parsed=parsed, contract_valid=valid,
                          verdict='PASS' if valid and all(parsed[f] is False for f in FIELDS) else 'BLOQUEO_CONTRATO')
        else:
            parsed = validate_response(response)
            record.update(parsed=parsed.model_dump(), contract_valid=True, verdict=verdict(parsed))
        record['state'] = 'completed'
    except Exception as exc:
        record.update(state='error', error_type=type(exc).__name__, verdict='BLOQUEO_CONTRATO')
    record['duration_seconds'] = round(time.monotonic() - started, 3)
    save(target, record)
    print(json.dumps({k: record.get(k) for k in ('name', 'contract_valid', 'verdict', 'estimated_usd')}), flush=True)
    return record


def summarize(directory, phase, records, passed, **details):
    result = {'phase': phase, 'contract_version': VERSION, 'pass': passed,
              'contract_sha256': configuration_digest(),
              'records': [r['name'] + '.json' for r in records], 'details': details,
              'cost_confirmed': all(r['cost_confirmed'] for r in records),
              'known_estimated_usd': round(sum(r.get('estimated_usd') or 0 for r in records), 8),
              'swipes_sent': 0, 'production_policy_modified': False}
    save(directory / (phase + '_summary.json'), result)
    return result


async def phase_a(client, directory):
    image = SOURCE / 'p03.png'
    records = await asyncio.gather(*(
        inspect(client, directory, image, f'A{index}_i1', variant, phase='A')
        for index, variant in enumerate(('baseline', 'fewshot', 'observation_first'), 1)))
    candidates = [r for r in records[1:] if r['contract_valid'] and r['cost_confirmed']
                  and r['verdict'] == 'PASS']
    selected = candidates[0]['variant'] if candidates else None
    summarize(directory, 'A', records, bool(selected), selected=selected)
    return selected


async def phase_b(client, directory, variant):
    clean = [SOURCE / 'control_p01.png', ROOT / 'screenshots' / RUN / 'snapshot_07.png',
             ROOT / 'screenshots' / RUN / 'snapshot_06.png']
    mocks = [directory / 'mock_captcha.png', directory / 'mock_softblock.png']
    if not all(path.is_file() for path in mocks):
        raise ValueError('Missing labeled positive controls')
    async def b1():
        return await asyncio.gather(*(inspect(client, directory, image, f'B1_{index}_i1', variant,
                                               phase='B') for index, image in enumerate(clean, 1)))
    async def b2():
        return await asyncio.gather(*(inspect(client, directory, image, f'B2_{index}_i1', variant,
                                               phase='B') for index, image in enumerate(mocks, 1)))
    negative, positive = await asyncio.gather(b1(), b2())
    expected = ['captcha', 'softblock']
    negative_ok = all(r['contract_valid'] and r['verdict'] == 'PASS' and r['cost_confirmed'] for r in negative)
    positive_ok = all(r['contract_valid'] and r['cost_confirmed'] and r['parsed'][field] is True
                      for r, field in zip(positive, expected))
    records = [*negative, *positive]
    return summarize(directory, 'B', records, negative_ok and positive_ok,
                     clean_pass=negative_ok, challenges_detected=positive_ok,
                     clean_control_duplicates='control_p01 is the same original image as p01; two independent queries',
                     positive_control_type='synthetic browser UI; not a real account challenge')


async def hardware_phase(client, directory, variant, phase, inventory):
    from core.database import Database
    from core.device_map import _derive_ref
    from core.mass_orchestrator import bloquear_granja
    from core.panda_api import PandaClient
    from core.panda_inventory import obtener_inventario
    from main_panda_masivo import canonical_selection
    from types import SimpleNamespace
    limit = 10 if phase == 'C' else 34
    if phase == 'D' and not json.loads((directory / 'C_summary.json').read_text())['pass']:
        raise ValueError('Phase C has not passed')
    accepted = json.loads((directory / 'B_summary.json').read_text())
    if not accepted['pass'] or accepted.get('contract_sha256') != configuration_digest():
        raise ValueError('Phase B has not passed')
    if phase == 'D' and json.loads((directory / 'C_summary.json').read_text()).get('contract_sha256') != configuration_digest():
        raise ValueError('Phase C contract differs from current contract')
    chosen = canonical_selection(SimpleNamespace(inventory=inventory, expected_count=10))
    _, live, _ = await obtener_inventario(Database())
    verified = [row for row in live if row['estado'] == 'vinculado']
    by_serial = {row['serial_fisico']: row for row in verified}
    selected = []
    for item in chosen:
        row = by_serial.get(item['serial'])
        if not row or row['transporte'] != item['transporte']:
            raise ValueError('Hardware identity no longer matches admission')
        selected.append((item['map_plate'], item['device_ref'], row))
    if phase == 'D':
        selected_serials = {r['serial_fisico'] for _, _, r in selected}
        for row in sorted(verified, key=lambda r: int(r['numero_panda'])):
            if row['serial_fisico'] in selected_serials:
                continue
            ref = _derive_ref(row['serial_fisico'], os.environ['PANDA_DEVICE_SALT'])
            selected.append((f'p{len(selected) + 1:02d}', ref, row))
            if len(selected) == limit:
                break
    if len(selected) != limit:
        raise ValueError('Hardware quota not met')
    panda = PandaClient(screenshots=directory / ('screenshots_' + phase),
                        expected_identities={row['numero_panda']: row['serial_fisico'] for _, _, row in selected})
    save(directory / (phase + '_inventory.json'), {
        'plates': [{'plate': plate, 'device_ref': ref, 'panda_id': row['numero_panda']}
                   for plate, ref, row in selected],
        'identity_basis': 'live Panda onlySerial joined with hardware ADB identity',
    })
    records = []
    with bloquear_granja(ROOT / 'sessions/farm.lock'):
        failures = await panda.preparar([row['numero_panda'] for _, _, row in selected])
        if failures:
            raise ValueError('Panda binding failed')
        for plate, ref, row in selected:
            image = await panda.capturar_pantalla_dispositivo_async(row['numero_panda'])
            result = await inspect(client, directory, image, f'{phase}_{plate}_i1', variant, phase=phase)
            result['device_ref'] = ref
            save(directory / (result['name'] + '.json'), result)
            records.append(result)
            if (not result['contract_valid'] or not result['cost_confirmed']
                    or result['verdict'] != 'PASS'):
                if phase == 'D':
                    break  # Completed request usage is persisted before stopping the batch.
        passed = len(records) == limit and all(r['verdict'] == 'PASS' and r['cost_confirmed'] for r in records)
    return summarize(directory, phase, records, passed, expected=limit,
                     completed=len(records), failures=[r['name'] for r in records if r['verdict'] != 'PASS'
                                                       or not r['cost_confirmed']],
                     unprocessed=[plate for plate, _, _ in selected[len(records):]])


async def main(args):
    directory = args.report.resolve()
    if not directory.is_dir() or not directory.is_relative_to(ROOT / 'runs'):
        raise ValueError('Private report directory required')
    load_project_environment()
    if not os.getenv('OPENAI_API_KEY'):
        raise ValueError('Missing API key')
    async with AsyncOpenAI(timeout=45, max_retries=0) as client:
        if args.phase == 'A':
            return bool(await phase_a(client, directory))
        chosen = json.loads((directory / 'A_summary.json').read_text())['details']['selected']
        if not chosen:
            raise ValueError('No selected contract')
        if args.phase == 'B':
            return (await phase_b(client, directory, chosen))['pass']
        return (await hardware_phase(client, directory, chosen, args.phase, args.inventory))['pass']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['A', 'B', 'C', 'D'], required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--inventory', type=Path,
                        default=ROOT / 'runs/lab_stage10_20261110T161649Z.csv')
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(main(args)) else 2)
