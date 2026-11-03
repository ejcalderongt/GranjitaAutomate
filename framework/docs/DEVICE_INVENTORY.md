# Device inventory for R1 decision

UTC: 2026-11-03T06:06:55.148566+00:00
Base commit: 188790f4b7f932c4f955ab65830d687648801686
Global command: adb devices -l (first configured server; endpoint omitted).
Authorization: A1..A5 read-only queries only; B1..B2 keep Appium required by default.
No retries. Per-command timeout: 10 seconds.

## Inventory

plate | uid | locale | timezone | sim_country | sim_country_status | automation_packages_count
p01 | 2000 | es-GT | America/Guatemala | None | unavailable | 6
p02 | 2000 | es-GT | America/Guatemala | None | unavailable | 5
p03 | 2000 | es-GT | America/Guatemala | None | unavailable | 5

## Detected automation packages

package | plates | found_in | context_hint | classification
com.genfarmer.uiautomator | p01,p02,p03 | none | none | residuo_probable
com.genfarmer.uiautomator.test | p01,p02,p03 | none | none | residuo_probable
com.topjohnwu.magisk | p01 | none | none | residuo_probable
io.appium.settings | p01,p02,p03 | scripts/audit_deployment.py:8; scripts/deploy_tools.py:88 | script | requerido_por_repo
io.appium.uiautomator2.server | p01,p02,p03 | scripts/audit_deployment.py:8; scripts/deploy_tools.py:86; scripts/deploy_tools.py:87 | script | requerido_por_repo
io.appium.uiautomator2.server.test | p01,p02,p03 | scripts/audit_deployment.py:8; scripts/deploy_tools.py:87 | script | requerido_por_repo

Patterns: appium, uiautomator, adbkit, selenium, atx, maestro, autojs, frida, xposed, magisk, scrcpy.

## Observaciones

- Labels follow this inventory order; historical physical binding is not asserted.
- Only the first configured ADB server was listed; no second-server query or reconnect.
- Package output was filtered in memory; raw package lists and real identifiers were not saved.
- Appium family references are dependency linkage, not necessarily exact package-name hits.
- Missing SIM country is unavailable, not evidence of a foreign SIM.
- Package classifications do not authorize removal.
- No device filesystem comparison was performed; read-only command compliance is the evidence.

## No se ha modificado nada

- No package was installed or removed; no device setting was changed by invoked commands.
- No SIM data was changed.
- .env, config/farm_policy.py, config/farm_preflight.py and config/proxies.py were not edited.
- main_panda.py, core/browser.py and tiktok_warmer/core/socks_bridge.py were not edited.
- No preflight, Vision, warmup, swipe or full-farm batch was executed.

## Pendientes para la decision R1

- Human decision on whether required Appium workflows remain necessary.
- Separate authorization before any package removal or locale/timezone adjustment.
- Missing SIM country requires a verifiable source; do not invent values.
- Integrity attestation and real historical metrics remain separate pending work.
