#!/usr/bin/env python3
"""Recompute saved test counts before publishing the Chinese research report."""

import json
from pathlib import Path
import sys
import hashlib
import csv
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.algorithms.metrics import aggregate, score_image

LABELS = {
    "original": "原始图像",
    "gamma": "Gamma",
    "clahe": "CLAHE",
    "retinex": "SSR Retinex",
    "adaptive": "自适应",
}


def percentage(value):
    return "未评估" if value is None else f"{value * 100:.2f}%"


def interval(value):
    return "未评估" if not value else f"{value[0] * 100:.2f}%–{value[1] * 100:.2f}%"


def main():
    from summarize_fixed_threshold import summarize

    reports = []
    for dataset in ["cbsr-nir", "yale-b"]:
        folder = ROOT / "experiments/results" / ("real-" + dataset)
        report = json.loads((folder / "summary.json").read_text())
        config = json.loads((folder / "protocol-frozen.json").read_text())
        assert report["status"] == "completed"
        assert (
            hashlib.sha256((folder / "protocol-frozen.json").read_bytes()).hexdigest()
            == report["protocol_sha256"]
        )
        assert (
            hashlib.sha256((folder / "benchmark-source-frozen.py").read_bytes()).hexdigest()
            == config["code_hashes"]["experiments/scripts/benchmark_public.py"]
        )
        thresholds = json.loads((folder / "thresholds-frozen.json").read_text())
        assert thresholds["thresholds"] == report["thresholds"]
        truths = {item["file"]: item["faces"] for item in config["test"]}
        rows = [
            json.loads(line) for line in (folder / "predictions.jsonl").read_text().splitlines()
        ]
        assert len(rows) == len(config["test"]) * len(config["methods"])
        assert all(
            count == 1 for count in Counter((row["file"], row["method"]) for row in rows).values()
        )
        for row in rows:
            recomputed = score_image(
                truths[row["file"]],
                row["predictions"],
                row["elapsed_ms"],
                protocol=config["protocol"]["localization_protocol"],
            )
            assert all(
                recomputed[key] == row[key]
                for key in ["tp", "fp", "fn", "known", "unknown", "correct", "false_accept"]
            )
            assert all(
                face["match"]["threshold"] == report["thresholds"][row["method"]]
                for face in row["predictions"]
            )
        for method in config["methods"]:
            actual = aggregate([row for row in rows if row["method"] == method])
            assert actual == report["summary"][method]["overall"]
        # Make a downloaded CSV self-describing even when separated from its JSON report.
        with (folder / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            keys = ["tp", "fp", "fn", "known", "unknown", "correct", "false_accept", "elapsed_ms"]
            writer.writerow(
                [
                    "dataset",
                    "profile",
                    "localization_protocol",
                    "detector_input",
                    "method",
                    "scene",
                    "file",
                    "threshold",
                    *keys,
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        dataset,
                        config.get("profile", "full"),
                        config["protocol"]["localization_protocol"],
                        config.get("detector_size", 640),
                        row["method"],
                        row["scene"],
                        row["file"],
                        report["thresholds"][row["method"]],
                        *[row[key] for key in keys],
                    ]
                )
        diagnostics = {}
        for method in config["methods"]:
            decisions = [
                d for row in rows if row["method"] == method for d in row["decisions"] if d["known"]
            ]
            threshold = report["thresholds"][method]
            diagnostics[method] = {
                "missed_or_ambiguous": sum(not d["detected"] for d in decisions),
                "rejected_below_threshold": sum(
                    d["detected"] and (d["score"] is None or d["score"] < threshold)
                    for d in decisions
                ),
                "wrong_identity_accepted": sum(
                    d["detected"]
                    and d["score"] is not None
                    and d["score"] >= threshold
                    and d["candidate_id"] != d["truth_person_id"]
                    for d in decisions
                ),
            }
            assert sum(diagnostics[method].values()) + report["summary"][method]["overall"][
                "correct"
            ] == len(decisions)
        (folder / "failure-diagnostics.json").write_text(
            json.dumps(diagnostics, ensure_ascii=False, indent=2)
        )
        secondary = summarize(folder)
        reports.append((report, config, secondary, diagnostics))
    lines = [
        "# 真实公开数据评估报告",
        "",
        "日期：2026-10-17。以下计数已从保存的逐样本预测重新核对。所有成绩均来自真实预训练模型推理，没有用合成压暗图替代真实采集。",
        "",
        "本次为资源受限环境下预先固定的研究子集，完整归档已下载，但未把完整数据规模写作已测规模。数据、算法、划分、阈值与证据范围见 public-benchmark-protocol.md。",
        "",
    ]
    for report, config, secondary, diagnostics in reports:
        lines += [
            "## " + report["title"],
            "",
            f"- 图库：{report['gallery_subjects']} 人，{report['gallery_accepted_images']}/{report['gallery_images']} 张参考照片可用。注册失败不会移除对应已知查询。",
            f"- 校准：{report['calibration_images']} 张；测试：{report['test_images']} 张。检测输入 {config['detector_size']}×{config['detector_size']}，CPU {report['workers']} 个工作进程。",
            f"- 定位协议：`{report['protocol']['localization_protocol']}`；这不是 IoU 检测基准。",
            f"- 原始数据 SHA-256：`{config['archive_sha256']}`。",
            "",
            "| 方法 | 已知正确/总数 | 确认率 | Wilson 95% 区间 | 人员重采样区间 | 未知误接受/总数 | 未知 FAR |",
            "|---|---:|---:|---|---|---:|---|",
        ]
        for method, value in report["summary"].items():
            stats = value["overall"]
            lines.append(
                f"| {LABELS[method]} | {stats['correct']}/{stats['known']} | {percentage(stats['confirmation_rate'])} | {interval(stats['confirmation_ci95'])} | {interval(stats['confirmation_subject_bootstrap_ci95'])} | {stats['false_accept']}/{stats['unknown']} | {percentage(stats['unknown_far'])}（95% 区间 {interval(stats['unknown_far_ci95'])}） |"
            )
        lines += [
            "",
            "失败分解（全部已知查询；漏检或单脸歧义保留在分母）：",
            "",
            "| 方法 | 漏检/歧义 | 低于阈值拒绝 | 错误身份接受 |",
            "|---|---:|---:|---:|",
        ]
        for method, counts in diagnostics.items():
            lines.append(
                f"| {LABELS[method]} | {counts['missed_or_ambiguous']} | {counts['rejected_below_threshold']} | {counts['wrong_identity_accepted']} |"
            )
        lines += [
            "",
            "各方法分别在校准集以经验 FAR≤1% 选阈值。小规模校准的 0 次误接受无法证明总体 FAR≤1%；观察到的增强差异还包含阈值差异，不能直接归因于图像增强。",
        ]
        lines += [
            "",
            "补充对照：软件原有固定阈值 0.45（探索性，未用测试标签选择）",
            "",
            "| 方法 | 已知正确/总数 | 确认率 | 未知误接受/总数 | FAR |",
            "|---|---:|---:|---:|---:|",
        ]
        for method, stats in secondary["summary"].items():
            lines.append(
                f"| {LABELS[method]} | {stats['correct']}/{stats['known']} | {percentage(stats['confirmation_rate'])} | {stats['false_accept']}/{stats['unknown']} | {percentage(stats['unknown_far'])}（95% 区间 {interval(stats['unknown_far_ci95'])}） |"
            )
        lines += [
            "",
            "该值是下载研究数据前就存在的演示默认值，未通过当前独立校准。它用于展示同一阈值下的增强影响，不替换主协议结果，也不能作为夜间或实景目标达标证据。",
        ]
        lines += [
            "",
            "各场景（自适应组）：",
            "",
            "| 源场景 | 已知正确/总数 | 确认率 | 未知误接受/总数 |",
            "|---|---:|---:|---:|",
        ]
        for scene, stats in report["summary"]["adaptive"]["scenes"].items():
            label = report["protocol"]["scene_labels"].get(scene, scene)
            lines.append(
                f"| {label} | {stats['correct']}/{stats['known']} | {percentage(stats['confirmation_rate'])} | {stats['false_accept']}/{stats['unknown']} |"
            )
        lines += ["", "考核目标证据：", ""]
        for scene, value in report["summary"]["adaptive"]["targets"].items():
            label = {
                "infrared": "夜间主动近红外 95%",
                "backlight": "实景强逆光 90%",
                "overall": "真实三场景综合 95%",
            }[scene]
            lines.append(
                f"- {label}：**{value['status']}**。" + "；".join(value.get("reasons", []))
            )
        lines += [
            "",
            "分方法冻结阈值：`" + json.dumps(report["thresholds"], ensure_ascii=False) + "`。",
            "",
            "限制：" + "；".join(report["protocol"]["limitations"]) + "。",
            "",
        ]
    lines += [
        "## 可以得出的结论",
        "",
        "系统已补上真实公开近红外及受控可见光数据的可复现评估，能查看确认成功、漏检、未知拒识和增强前后的实际变化。五组结果均保留，不根据测试成绩回头修改阈值或删掉困难图片。",
        "",
        "公开近红外数据没有明确夜间及跨会话证据；Yale 的短时受控光照不是独立实景低照度/逆光采集。因此不能把这些研究成绩直接写成三个现场考核目标已达标。IR 同模态结果不代表 RGB→IR。预训练模型的原始训练身份与公开基准是否完全互斥也未能独立核查。",
        "",
        "补齐现场验收需要按 field-study-protocol.md 采集独立会话与真实照明/设备日志，再用 audit_field_data.py 检查并导入。空模板的审计输出会明确列出缺口，不产生虚构结果。",
        "",
        "原始图片不进入源码包或下载输出，公开结果仅含伪名编号、框/眼点、预测分数及计数。运行时长是并发 CPU 记录，不作为独占硬件时延基准。",
    ]
    destination = ROOT / "docs/real-data-evaluation.md"
    destination.write_text("\n".join(lines) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
