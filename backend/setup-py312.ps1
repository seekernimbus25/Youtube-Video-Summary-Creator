$ErrorActionPreference = "Stop"

$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $backendDir ".venv312"
$pythonExe = Join-Path $venvDir "Scripts\\python.exe"
$tempDir = Join-Path $backendDir ".tmp-py312"

New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$env:TMP = $tempDir
$env:TEMP = $tempDir

Write-Host "Creating Python 3.12 virtual environment in $venvDir"
py -3.12 -m venv $venvDir

Write-Host "Upgrading pip"
& $pythonExe -m pip install --upgrade pip

Write-Host "Installing backend development dependencies"
& $pythonExe -m pip install -r (Join-Path $backendDir "requirements-dev.txt")

Write-Host ""
Write-Host "Backend Python 3.12 environment is ready."
Write-Host "Activate: $venvDir\\Scripts\\Activate.ps1"
Write-Host "Run server: .\\run-dev-py312.ps1"
