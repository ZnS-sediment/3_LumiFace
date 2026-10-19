#!/usr/bin/env python3
"""Render measured synthetic-lighting results; never substitutes field target evidence."""

import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {
    "original": "不增强",
    "gamma": "Gamma",
    "clahe": "CLAHE",
    "retinex": "Retinex",
    "adaptive": "自适应",
}
SCENES = {
    "normal": "原始基线",
    "low_light": "模拟低照度",
    "backlight": "模拟逆光",
    "pseudo_infrared": "模拟灰度补光",
}


def main():
    folder = ROOT / "experiments/results/simulated-att-lighting"
    data = json.loads((folder / "summary.json").read_text())
    if data["real_capture"] or data["field_validation"]:
        raise ValueError("This renderer only accepts explicitly simulated results")
    rows = []
    unknown = []
    targets = []
    target_report = {}
    for method, label in METHODS.items():
        group = data["summary"][method]
        cells = "".join(
            f"<td>{v['correct']} / {v['known']}<small>{v['confirmation_rate'] * 100:.2f}%</small></td>"
            for v in group["scenes"].values()
        )
        pooled = group["pooled_visible_three_scenes"]
        rows.append(
            f"<tr><th>{label}</th>{cells}<td>{pooled['correct']} / {pooled['known']}<small>{pooled['confirmation_rate'] * 100:.2f}%</small></td></tr>"
        )
        far = "".join(
            f"<td>{group['scenes'][s]['false_accept']} / {group['scenes'][s]['unknown']}</td>"
            for s in SCENES
        )
        unknown.append(f"<tr><th>{label}</th>{far}</tr>")
        checks = [
            ("模拟灰度补光", group["scenes"]["pseudo_infrared"], 0.95),
            ("模拟逆光", group["scenes"]["backlight"], 0.90),
            ("前三类合并", pooled, 0.95),
        ]
        target_report[method] = {
            name: {
                "target": goal,
                "correct": item["correct"],
                "known": item["known"],
                "observed": item["confirmation_rate"],
                "observed_meets_simulated_target": item["confirmation_rate"] >= goal,
            }
            for name, item, goal in checks
        }
        cells = "".join(
            f"<td>{item['confirmation_rate'] * 100:.2f}% / {goal * 100:.0f}%<small>{'达到模拟目标' if item['confirmation_rate'] >= goal else '未达到模拟目标'}</small></td>"
            for name, item, goal in checks
        )
        targets.append(f"<tr><th>{label}</th>{cells}</tr>")
    preview = ROOT / "work/simulated-lighting-preview.png"
    picture = ""
    if preview.exists():
        picture = (
            '<img alt="同一身份四种模拟场景预览" src="data:image/png;base64,'
            + base64.b64encode(preview.read_bytes()).decode()
            + '">'
        )
    headings = "".join("<th>" + label + "</th>" for label in SCENES.values())
    source = html.escape(data["model_fingerprint"])
    page = (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LumiFace 模拟光照测试报告</title><style>body{font-family:"Microsoft YaHei",sans-serif;color:#263445;background:#f5f6f8;max-width:1080px;margin:30px auto;padding:20px;line-height:1.8}main{background:white;padding:28px;border:1px solid #dce1e7}h1{font-size:26px}h2{font-size:20px;margin-top:28px}.scope{color:#775000;background:#fff6e5;border-left:4px solid #b57a00;padding:12px 16px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #dce1e7;padding:10px;text-align:left}thead{background:#f3f5f7}small{display:block;color:#526071}img{display:block;width:100%;height:auto}code{overflow-wrap:anywhere}.scroll{overflow:auto}</style><main><h1>LumiFace 模拟复杂光照压力测试</h1><p class="scope">软件模拟数据 · 真实模型预测 · 非真实场景验收。此报告不证明 95%／90%／95% 实景目标已达标。</p><p>40 名已知身份，120 张注册参考；校准已知 320 张、未知 4 张；测试已知 800 张、未知 4 张。每种方法分别在校准集冻结阈值，保留全部测试失败。未知校准与未知测试各仅一个来源人物，误接受结果不代表一般保障。</p>"""
        + picture
        + '<h2>身份确认：正确数 / 已知查询数</h2><div class="scroll"><table><thead><tr><th>方法</th>'
        + headings
        + "<th>前三类合并</th></tr></thead><tbody>"
        + "".join(rows)
        + '</tbody></table></div><h2>未知误接受：次数 / 未知查询数</h2><div class="scroll"><table><thead><tr><th>方法</th>'
        + headings
        + "</tr></thead><tbody>"
        + "".join(unknown)
        + "</tbody></table></div><h2>条件与复现</h2><p>输入为确定性曝光、阴影、眩光和噪声模拟；AT&T 本身为灰度图，模拟灰度补光不代表真实红外光谱采集。同一源图的变体相关，图库、校准、测试已按原始文件划分，独立采集会话尚未建立。</p><p>检测输入 320×320，真实 buffalo_l / SCRFD / ArcFace，CPU 并发 2 个工作进程；与网页默认 640×640 配置分别说明。这里只评价单人脸存在性后的身份确认，不作 IoU 人脸框精度结论。</p><p>数据致谢 AT&T Laboratories Cambridge。未知功能样例来自 scikit-image astronaut / Matplotlib grace_hopper。详细源照片与摘要随数据包提供。</p><p>模型指纹：<code>"
        + source
        + "</code></p><p>逐样本预测、冻结参数及校准阈值保存在 experiments/results/simulated-att-lighting。</p></main></html>"
    )
    target_table = (
        '<h2>三项模拟目标对照</h2><p>仅比较模拟数据的观测比例；达到模拟目标不等于实景验收通过。</p><div class="scroll"><table><thead><tr><th>方法</th><th>模拟灰度补光 / 95%</th><th>模拟逆光 / 90%</th><th>前三类合并 / 95%</th></tr></thead><tbody>'
        + "".join(targets)
        + "</tbody></table></div>"
    )
    page = page.replace("<h2>未知误接受", target_table + "<h2>未知误接受")
    (folder / "simulation-target-comparison.json").write_text(
        json.dumps(
            {
                "real_capture": False,
                "field_validation": False,
                "comparison": "point estimates on simulated data only",
                "methods": target_report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    (folder / "report.html").write_text(page)
    print(folder / "report.html")


if __name__ == "__main__":
    main()
