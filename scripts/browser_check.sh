#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p work
export LUMIFACE_TEST_API_PORT="${LUMIFACE_TEST_API_PORT:-8000}"
export LUMIFACE_TEST_UI_PORT="${LUMIFACE_TEST_UI_PORT:-5173}"
export LUMIFACE_API_URL="http://127.0.0.1:$LUMIFACE_TEST_API_PORT"
export LUMIFACE_UI_ORIGIN="http://127.0.0.1:$LUMIFACE_TEST_UI_PORT"
export LUMIFACE_TEST_BASE_URL="$LUMIFACE_UI_ORIGIN"
.venv/bin/python scripts/prepare_browser_fixtures.py
.venv/bin/python - <<'PY'
import socket,os
for port in (int(os.environ['LUMIFACE_TEST_API_PORT']),int(os.environ['LUMIFACE_TEST_UI_PORT'])):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:s.bind(('127.0.0.1',port))
        except OSError:raise SystemExit(f'浏览器测试需要空闲端口 {port}，请先停止开发服务器')
PY
TEST_RUNTIME="$(mktemp -d "${TMPDIR:-/tmp}/lumiface-browser-XXXXXX")"
export LUMIFACE_TEST_DELETE_ISOLATED=1
backend_pid=''
frontend_pid=''
cleanup(){
  trap - EXIT INT TERM
  if [ -n "$frontend_pid" ]; then kill -- -"$frontend_pid" 2>/dev/null || true; fi
  if [ -n "$backend_pid" ]; then kill -- -"$backend_pid" 2>/dev/null || true; fi
  if [ -n "$frontend_pid" ]; then wait "$frontend_pid" 2>/dev/null || true; fi
  if [ -n "$backend_pid" ]; then wait "$backend_pid" 2>/dev/null || true; fi
  rm -rf -- "$TEST_RUNTIME"
}
trap cleanup EXIT INT TERM
setsid env LUMIFACE_NATIVE_PICKER=0 LUMIFACE_DATA="$TEST_RUNTIME" .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$LUMIFACE_TEST_API_PORT" > work/browser-backend.log 2>&1 &
backend_pid=$!
setsid npm run dev --prefix frontend -- --port "$LUMIFACE_TEST_UI_PORT" > work/browser-frontend.log 2>&1 &
frontend_pid=$!
.venv/bin/python - <<'PY'
import time,urllib.request,os
for address in (os.environ['LUMIFACE_API_URL']+'/api/system/overview',os.environ['LUMIFACE_UI_ORIGIN']):
    for attempt in range(300):
        try:
            with urllib.request.urlopen(address,timeout=2) as r:
                if r.status==200:break
        except OSError:time.sleep(.2)
    else:raise SystemExit(f'Server startup failed: {address}')
# Prove startup loaded the real model without issuing a manual load request.
with urllib.request.urlopen(os.environ['LUMIFACE_API_URL']+'/api/system/model',timeout=10) as response:
    import json
    if not json.load(response)['data']['ready']:raise SystemExit('Automatic model startup failed')
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
frontend/node_modules/.bin/playwright test -c frontend/playwright.config.ts "$@"
