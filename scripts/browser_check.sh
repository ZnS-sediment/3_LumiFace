#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work
.venv/bin/python scripts/prepare_browser_fixtures.py
.venv/bin/python - <<'PY'
import socket
for port in (8000,5173):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:s.bind(('127.0.0.1',port))
        except OSError:raise SystemExit(f'浏览器测试需要空闲端口 {port}，请先停止开发服务器')
PY
TEST_RUNTIME="$(mktemp -d "$ROOT/work/browser-run-XXXXXX")"
backend_pid=''
frontend_pid=''
cleanup(){
  trap - EXIT INT TERM
  if [ -n "$frontend_pid" ]; then kill -- -"$frontend_pid" 2>/dev/null || true; fi
  if [ -n "$backend_pid" ]; then kill -- -"$backend_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
setsid env LUMIFACE_DATA="$TEST_RUNTIME" .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 > work/browser-backend.log 2>&1 &
backend_pid=$!
setsid npm run dev --prefix frontend > work/browser-frontend.log 2>&1 &
frontend_pid=$!
.venv/bin/python - <<'PY'
import time,urllib.request
for address in ('http://127.0.0.1:8000/api/system/overview','http://127.0.0.1:5173'):
    for attempt in range(100):
        try:
            with urllib.request.urlopen(address,timeout=2) as r:
                if r.status==200:break
        except OSError:time.sleep(.2)
    else:raise SystemExit(f'Server startup failed: {address}')
PY
# The verified WSL host uses its existing Windows fonts for headless screenshots.
if [ -d /mnt/c/Windows/Fonts ]; then
  cat > work/fonts.conf <<XML
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><dir>/usr/share/fonts</dir><dir>/mnt/c/Windows/Fonts</dir><cachedir>$ROOT/work/font-cache</cachedir><include ignore_missing="yes">/etc/fonts/conf.d</include></fontconfig>
XML
  export FONTCONFIG_FILE="$ROOT/work/fonts.conf"
fi
# Optional local browser libraries on minimal WSL; normal desktop Linux uses system packages.
if [ -d work/browser-libs/extracted/usr/lib/x86_64-linux-gnu ]; then
  export LD_LIBRARY_PATH="$ROOT/work/browser-libs/extracted/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
frontend/node_modules/.bin/playwright test -c frontend/playwright.config.ts
