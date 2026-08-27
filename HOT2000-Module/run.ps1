$ErrorActionPreference = "Stop"
$moduleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $moduleRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
}

.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000