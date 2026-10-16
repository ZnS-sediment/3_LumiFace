$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) { throw '请先执行 py -3.11 -m venv .venv 并安装依赖；WSL 项目请使用 bash scripts/start.sh' }
$Backend = Start-Process -FilePath $Python -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8000' -PassThru -NoNewWindow
try { npm run dev --prefix frontend } finally { Stop-Process -Id $Backend.Id -ErrorAction SilentlyContinue }
