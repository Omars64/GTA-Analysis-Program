$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ErrorActionPreference = 'Stop'
Set-Location "$root\backend"
if (!(Test-Path .venv)) {
  py -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
& .\.venv\Scripts\python.exe app.py
