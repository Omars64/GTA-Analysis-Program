$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $root 'backend\runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($service in @('backend', 'frontend')) {
  $port = if ($service -eq 'backend') { 5000 } else { 5173 }
  if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    Write-Host "Port $port is already occupied; no duplicate $service process started."
    continue
  }
  $script = Join-Path $root "start_$service.ps1"
  Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $script + '"') -RedirectStandardOutput (Join-Path $runtime "$service-$stamp.log") -RedirectStandardError (Join-Path $runtime "$service-$stamp-error.log")
}
Write-Host "Starting GTA Intelligence. Logs: $runtime"
Write-Host 'Open http://localhost:5173 once both services are ready.'
