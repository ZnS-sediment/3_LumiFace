#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
.venv/bin/python scripts/download_research_data.py cbsr-nir
.venv/bin/python scripts/download_research_data.py yale-b
# Sequential datasets bound memory use on the verified 7 GB WSL host.
.venv/bin/python experiments/scripts/benchmark_public.py cbsr-nir --profile pilot --workers 2 --detector-size 320
.venv/bin/python experiments/scripts/benchmark_public.py yale-b --profile pilot --workers 2 --detector-size 320
.venv/bin/python scripts/render_research_report.py
