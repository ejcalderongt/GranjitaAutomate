@echo off
rem Opcional: crea una regla de firewall para los clientes de la granja.
pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "scripts\Solicitar-ProxyLocal-Admin.ps1"
if errorlevel 1 goto done
".venv\Scripts\python.exe" "scripts\verificar_proxy_local.py" --enable
:done
popd
pause
