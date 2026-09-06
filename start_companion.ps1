$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process powershell -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File',"$root\start_backend.ps1"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$root\frontend'; if (!(Test-Path node_modules)) { npm install }; npm run dev"
Start-Sleep -Seconds 2
Start-Process 'http://localhost:5173'
