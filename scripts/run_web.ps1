param(
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = $null
$defaultWhisperPython = Join-Path $env:USERPROFILE "miniconda3\envs\whisper\python.exe"
$defaultWhisperPythonUpper = Join-Path $env:USERPROFILE "miniconda3\envs\WHISPER\python.exe"

if (Test-Path (Join-Path $ProjectRoot ".venv\\Scripts\\python.exe")) {
    $python = Resolve-Path (Join-Path $ProjectRoot ".venv\\Scripts\\python.exe")
} elseif (Test-Path $defaultWhisperPython) {
    $python = Resolve-Path $defaultWhisperPython
} elseif (Test-Path $defaultWhisperPythonUpper) {
    $python = Resolve-Path $defaultWhisperPythonUpper
} elseif ($env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX "python.exe"))) {
    $python = Resolve-Path (Join-Path $env:CONDA_PREFIX "python.exe")
} elseif (Get-Command conda -ErrorAction SilentlyContinue) {
    $condaEnv = conda env list 2>$null | Where-Object { $_ -match "^\s*whisper\s+" } | Select-Object -First 1
    if ($condaEnv) {
        $envPath = ($condaEnv -split "\s+")[-1]
        $envPython = Join-Path $envPath "python.exe"
        if (Test-Path $envPython) {
            $python = Resolve-Path $envPython
        }
    }
}

if (-not $python) {
    $python = "python"
}

Write-Host "Starting Local Whisper Studio on http://127.0.0.1:$Port"
Set-Location $ProjectRoot
Write-Host "Using Python: $python"

$depsOk = $true
try {
    & $python -c "import av, fastapi, faster_whisper" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $depsOk = $false
    }
} catch {
    $depsOk = $false
}

if (-not $depsOk) {
    Write-Host "Missing dependencies in the selected Python environment." -ForegroundColor Red
    Write-Host "Please do one of the following:" -ForegroundColor Yellow
    Write-Host "1. Activate your conda environment, then run this script again"
    Write-Host "2. Create .venv and install dependencies with: pip install -r requirements.txt"
    exit 1
}

& $python -m uvicorn app:app --app-dir $ProjectRoot --host 127.0.0.1 --port $Port --reload --reload-dir $ProjectRoot
