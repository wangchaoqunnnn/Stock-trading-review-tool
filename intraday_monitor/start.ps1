$ErrorActionPreference = "Stop"
$python = "C:\Users\HUAWEI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process -FilePath $python -ArgumentList "server.py", "--port", "8765" -WorkingDirectory $dir -WindowStyle Hidden
Write-Output "monitor started at http://127.0.0.1:8765"
