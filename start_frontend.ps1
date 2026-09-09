$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$root\frontend"
if (!(Test-Path node_modules)) {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
}
npm run dev -- --strictPort
