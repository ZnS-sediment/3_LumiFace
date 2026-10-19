"""Read only local public-benchmark reports. Never expose raw benchmark photos/vectors."""

import json
from pathlib import Path
from app.core.config import ROOT
from app.core.errors import AppError

BENCHMARKS = {"cbsr-nir": "real-cbsr-nir", "yale-b": "real-yale-b"}


def benchmark_file(dataset: str, filename: str) -> Path:
    if dataset not in BENCHMARKS or filename not in {
        "summary.json",
        "results.csv",
        "protocol-frozen.json",
    }:
        raise AppError("研究报告不存在", 404)
    path = ROOT / "experiments" / "results" / BENCHMARKS[dataset] / filename
    if not path.is_file():
        raise AppError("真实数据评估尚未完成，请先运行对应 benchmark 脚本", 404)
    return path


def reports() -> list[dict]:
    result = []
    for identity in BENCHMARKS:
        try:
            path = benchmark_file(identity, "summary.json")
        except AppError:
            continue
        try:
            record = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue  # A concurrently published report is not yet complete.
        if (
            isinstance(record, dict)
            and record.get("status") == "completed"
            and record.get("dataset") == identity
        ):
            result.append(record)
    return result
