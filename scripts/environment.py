#!/usr/bin/env python3
"""Optional PyTorch diagnostics, independent of the ONNX inference pipeline."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.experiments import environment

report = environment()
report["cpu_logical_cores"] = os.cpu_count()
try:
    import torch

    report["torch"] = {
        "version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda,
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
    }
except ImportError:
    report["torch"] = {
        "installed": False,
        "note": "Optional; InsightFace inference runs via ONNX Runtime",
    }
print(json.dumps(report, ensure_ascii=False, indent=2))
