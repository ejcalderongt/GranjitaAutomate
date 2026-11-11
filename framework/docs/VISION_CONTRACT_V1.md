# Visible UI contract v1

The selected experiment uses gpt-4o-mini, strict Structured Outputs, mandatory
boolean captcha, softblock and logged_out fields, and per-field confidence
in the range 0.01 to 1. The few-shot example is illustrative; positive controls
must also be detected before accepting a candidate.

Flags concern visible interface elements. They cannot certify hidden account,
server or authentication state. Confidence is self-reported and uncalibrated.
An unassessable screenshot sets evaluable=false and blocks the consumer.
A non-feed screenshot also blocks admission. No null-to-false conversion exists.
Truncation, refusal, malformed fields and missing usage block the diagnostic.

The implementation is in core/vision_contract.py. The read-only diagnostic
is scripts/validar_vision_v1.py. Its only hardware commands are inventory reads
and screenshots through verified Panda bindings. It exposes phases A, B, C, D.
It has no gesture or application-launch operation.

Each request is logged under a private runs/ directory. The complete API
response and usage are persisted before parsing, along with the schema,
prompt text, image path, image hash and evaluation. Retries are disabled.
Existing evidence is never replaced and the per-branch limit is three.
The original run and original diagnostic are preserved.

Phase A compares the nullable baseline, mandatory fields plus a complete
example, and an observation-first prompt. Phase B compares clean archived
frames with labeled synthetic challenge controls. Phase C evaluates ten new
hardware screenshots. Phase D requires C to pass, verifies 34 physical
identities, and stops on the first blocking observation or unverifiable cost.
Its inventory includes unprocessed devices when a batch stops early.

Run commands from the framework root, using the private report directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.validar_vision_v1 --phase A --report runs/<report>
.\.venv\Scripts\python.exe -m scripts.validar_vision_v1 --phase B --report runs/<report>
.\.venv\Scripts\python.exe -m scripts.validar_vision_v1 --phase C --report runs/<report>
.\.venv\Scripts\python.exe -m scripts.validar_vision_v1 --phase D --report runs/<report>
```

The production gesture orchestrator continues to use its existing contract.
Promotion of this diagnostic contract to gesture execution requires a separate
acceptance decision. The current request prohibits swipes globally.

API contract reference:
https://developers.openai.com/api/docs/guides/structured-outputs
