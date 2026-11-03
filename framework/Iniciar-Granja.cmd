@echo off
pushd "%~dp0"
".venv\Scripts\python.exe" main.py --start-farm --devices 40 --cycles 0 --bootstrap-parallelism 40
popd
pause
