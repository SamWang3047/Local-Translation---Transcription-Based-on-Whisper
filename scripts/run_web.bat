@echo off
set PORT=%1
if "%PORT%"=="" set PORT=8010
set PROJECT_ROOT=%~dp0..
set PYTHON=
set DEFAULT_WHISPER=%USERPROFILE%\miniconda3\envs\whisper\python.exe
set DEFAULT_WHISPER_UPPER=%USERPROFILE%\miniconda3\envs\WHISPER\python.exe

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
  set PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe
)

if not defined PYTHON (
  if exist "%DEFAULT_WHISPER%" set PYTHON=%DEFAULT_WHISPER%
)

if not defined PYTHON (
  if exist "%DEFAULT_WHISPER_UPPER%" set PYTHON=%DEFAULT_WHISPER_UPPER%
)

if not defined PYTHON (
  if defined CONDA_PREFIX (
    if exist "%CONDA_PREFIX%\python.exe" (
      set PYTHON=%CONDA_PREFIX%\python.exe
    )
  )
)

if not defined PYTHON (
  for /f "tokens=1,*" %%A in ('conda env list ^| findstr /R /I "^whisper " 2^>nul') do (
    if exist "%%B\python.exe" set PYTHON=%%B\python.exe
  )
)

if not defined PYTHON (
  set PYTHON=python
)

echo Starting Local Whisper Studio on http://127.0.0.1:%PORT%
echo Using Python: %PYTHON%
pushd "%PROJECT_ROOT%"
"%PYTHON%" -c "import av, fastapi, faster_whisper" >nul 2>nul
if errorlevel 1 (
  echo Missing dependencies in the selected Python environment.
  echo Activate your conda environment or create .venv and run: pip install -r requirements.txt
  popd
  exit /b 1
)
"%PYTHON%" -m uvicorn app:app --app-dir "%PROJECT_ROOT%" --host 127.0.0.1 --port %PORT% --reload --reload-dir "%PROJECT_ROOT%"
popd
