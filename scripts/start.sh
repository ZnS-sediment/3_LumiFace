#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo '请先运行 bash scripts/setup.sh（Python 3.11+、Node.js 20.19+）'; exit 1
fi
.venv/bin/python - <<'PY'
import socket
for port in (8000, 5173):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: sock.bind(('127.0.0.1', port))
        except OSError: raise SystemExit(f'端口 {port} 已占用，请先关闭占用它的服务')
PY
backend_pid=''
frontend_pid=''
cleanup() {
  trap - EXIT INT TERM
  if [ -n "$frontend_pid" ]; then kill -- -"$frontend_pid" 2>/dev/null || true; fi
  if [ -n "$backend_pid" ]; then kill -- -"$backend_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
setsid .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
backend_pid=$!
setsid npm run dev --prefix frontend &
frontend_pid=$!
printf '\n网页入口（在浏览器打开）: http://localhost:5173\n后端接口文档: http://localhost:8000/docs\n按 Ctrl+C 停止前后端。服务启动时自动加载人脸模型，无需手动操作。\n\n'
wait -n "$backend_pid" "$frontend_pid"
