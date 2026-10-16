#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
.venv/bin/python -m pip check
.venv/bin/python -m pytest -c backend/pytest.ini backend/tests -q
npm run build --prefix frontend
if [ "${REAL_MODEL_TEST:-0}" = '1' ]; then .venv/bin/python scripts/smoke_real_model.py; fi
