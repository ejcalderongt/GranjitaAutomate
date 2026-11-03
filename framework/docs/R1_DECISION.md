# R1 geographic decision proposal

Base commit: 7354cd7. Proposal only; no device or environment changes executed.
Evidence: docs/DEVICE_INVENTORY.md:12-14 reports three current inventory labels.
All report locale es-GT, timezone America/Guatemala and unavailable SIM country.
These settings identify configuration, not physical location or SIM nationality.
The previously accredited proxy target is ES; no new network probe was run.

## Options

A: Keep effective country ES; align supported locale to es_ES or es-ES and
   timezone to Europe/Madrid through normal Android settings, after approval.
   Preserves the accredited proxy target; medium operational cost on three devices.
   SIM remains unaccredited: C2 could become WARN, not PASS, if other checks match.
B: Adopt GT as the human-approved operating target; retain current device settings.
   Requires PANDA_POLICY_COUNTRY=GT and a provider-configured GT proxy pool.
   PANDA_PROXY_COUNTRY=GT must then validate that pool; changing this variable alone
   does not relocate the proxy. Network revalidation required; medium/high cost.
   SIM remains unaccredited: no guaranteed C2 PASS or stage authorization.
C: Empty PANDA_POLICY_COUNTRY is not a geography bypass or a permanent WARN mode.
   config/farm_policy.py:77 defaults empty, but main_panda_masivo.py:149-150
   inherits the proxy target in real mode. With the current ES target, C2 can
   still FAIL on locale/timezone. Resolving SIM alone does not fix those mismatches.

## Recommendation

Recommend A as the smallest technical change preserving the already approved ES
proxy target; the human must confirm ES remains the intended operating country.
No option resolves C1 automation findings, missing integrity or C5 real history.

## Proposed next-prompt actions; NOT executed here

1. Human selects A, B or C and explicitly authorizes each device/configuration change.
2. Read-only checks, using a private current inventory binding, per selected device:
   adb -s <device> shell getprop persist.sys.locale
   adb -s <device> shell getprop persist.sys.timezone
   adb -s <device> shell getprop gsm.sim.operator.iso-country
3. For approved A, these UI-opening commands require separate explicit approval:
   adb -s <device> shell am start -a android.settings.LOCALE_SETTINGS
   adb -s <device> shell am start -a android.settings.DATE_SETTINGS
   Operator selects the approved language/region and timezone in supported settings.
   UI availability and permissions depend on Android version; do not substitute
   setprop, spoof SIM data or bypass device-management restrictions.
4. Repeat only the read-only checks above after the approved changes.
5. Any .env edit requires explicit approval. A may explicitly declare
   PANDA_POLICY_COUNTRY=ES; it is currently an effective fallback, not proven
   to be an explicit declaration. B needs both target declarations and real GT pool.
6. A later separately authorized preflight must confirm zero locale/timezone
   mismatches; SIM may still keep C2 at WARN. Do not invent missing measurements.

## Pending

- Human geographic decision; no policy or threshold changed in this proposal.
- Appium stays required; Genfarmer/Magisk require a definitive human classification.
- No package removal, SIM modification, preflight, Vision or warmup authorized here.
- C1 integrity channel and C5 real historical observations remain unresolved.
