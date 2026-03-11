param(
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"

if (Test-Path ".venv\\Scripts\\python.exe") {
    $python = Resolve-Path ".venv\\Scripts\\python.exe"
} else {
    $python = "python"
}

Write-Host "Starting Local Whisper Studio on http://127.0.0.1:$Port"
& $python -m uvicorn app:app --host 127.0.0.1 --port $Port --reload
