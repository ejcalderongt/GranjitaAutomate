# Playbook E-3

Ejecutar desde la raiz del framework cuando el operador autorice cada corrida.
Antes de E-2, verificar que el proxy haya pasado su preflight aislado y que
las tres placas del CSV coincidan con el mapa DPAPI, las rutas esperadas y la
alineacion de idioma y zona horaria requerida.

## E-2. Preflight real de tres placas

```powershell
.\.venv\Scripts\python.exe main_panda_masivo.py --preflight-proxy --preflight-farm --expected-count 3 --inventory tests/fixtures/csv/lab_stage3.csv
```

Registrar codigo de salida y `runs/farm_preflight_<run_id>.json`. Pasar a E-3
solo con codigo 0, `synthetic: false`, C1/C2 PASS o WARN aceptables, C3/C4 PASS
y C5 WARN por muestras incompletas. Si aparece FAIL o un WARN inesperado,
resolverlo y obtener una nueva autorizacion antes de repetir.

## E-3. Una corrida fisica sin Vision

```powershell
.\.venv\Scripts\python.exe main_panda_masivo.py --execute-read-only --ready --preflight-proxy --preflight-farm --expected-count 3 --inventory tests/fixtures/csv/lab_stage3.csv --cycles 1 --concurrency 1 --hold-seconds 12
```

El operador observa captchas, softblocks y deslogueos por placa durante el
ciclo. Registrar cada observacion como incidente, sin incidente observado
o no evaluado. Los contadores automaticos de E-3 quedan NULL.
Exito operativo requiere codigo 0, `completed: true`, ciclo terminado y
auditorias de escrituras PASS en `runs/native_run_<run_id>.json`. Revisar
la evidencia del preflight con el mismo run ID. Registrar por separado la
cobertura de las observaciones humanas. Una salida 2 es una parada de
politica y requiere su razon. Abortar ante un incidente, perdida de control,
identidad incorrecta o auditoria fallida.

## Seguimiento

Abrir `http://127.0.0.1:8000` mientras el servidor local este activo. En
Evidencia disponible, seleccionar el preflight real por run ID. Seguir el
ciclo fisico desde la terminal y observar las placas. La UI muestra informes
filtrados y su boton Detener actua sobre la verificacion sintetica del panel.
Usar Ctrl+C en la terminal de la corrida para solicitar su cancelacion.

| Que hacer si... | Accion |
|---|---|
| Falla el proxy | Detener antes de E-3, guardar evidencia y resolver la verificacion del proxy. |
| Falla la alineacion | Detener la admision y verificar identidad, ruta, idioma y zona de esa placa. |
| Hay captcha, softblock o deslogueo | Cancelar, registrar placa e incidente y detener el escalado. |
