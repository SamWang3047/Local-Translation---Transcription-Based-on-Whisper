@echo off
set PORT=%1
if "%PORT%"=="" set PORT=8010

if exist ".venv\Scripts\python.exe" (
  set PYTHON=.venv\Scripts\python.exe
) else (
  set PYTHON=python
)

echo Starting Local Whisper Studio on http://127.0.0.1:%PORT%
%PYTHON% -m uvicorn app:app --host 127.0.0.1 --port %PORT% --reload
