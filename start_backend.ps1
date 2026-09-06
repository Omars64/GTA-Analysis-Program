$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\backend"
if (!(Test-Path .venv)) {
  py -m venv .venv
  & .\.venv\Scripts\Activate.ps1
  python -m pip install -r requirements.txt
} else {
  & .\.venv\Scripts\Activate.ps1
}
python app.py
