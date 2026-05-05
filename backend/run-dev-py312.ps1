$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $backendDir ".venv312\\Scripts\\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python 3.12 virtualenv not found at $pythonExe. Run .\\setup-py312.ps1 first."
}

Push-Location $backendDir
try {
    & $pythonExe -m uvicorn main:app --reload --port 8000
}
finally {
    Pop-Location
}
