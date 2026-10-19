"""Separate a measured benchmark score from evidence for the requested field targets."""

from typing import Any


def assess_target(
    scene: str,
    stats: dict[str, Any],
    *,
    real_capture: bool,
    independent_calibration: bool,
    protocol: dict[str, Any],
    coverage: bool = True,
) -> dict[str, Any]:
    target = 0.90 if scene == "backlight" else 0.95
    rate = stats["confirmation_rate"]
    reasons = []
    if not coverage or rate is None:
        return {
            "target": target,
            "observed": rate,
            "status": "未评估",
            "reasons": ["缺少所需场景的已知身份样本"],
        }
    if not real_capture:
        reasons.append("非真实独立采集数据")
    if not independent_calibration:
        reasons.append("未使用真实校准集冻结阈值")
    if protocol.get("capture_independence") != "session_disjoint":
        reasons.append("未证明采集会话独立")
    evidence = protocol.get("scene_evidence", {})
    required = ["normal", "low_light", "backlight"] if scene == "overall" else [scene]
    for required_scene in required:
        item = evidence.get(required_scene, {})
        if not item.get("source") or item.get("annotation_basis") not in (
            "dataset_metadata",
            "manual_capture_log",
        ):
            reasons.append(f"{required_scene} 缺少可追溯场景证据")
        if required_scene == "infrared" and not (
            item.get("modality") == "nir"
            and item.get("active_illumination")
            and item.get("night_confirmed")
        ):
            reasons.append("近红外模态、主动补光或夜间环境证据不足")
        if required_scene == "backlight" and not item.get("backlight_confirmed"):
            reasons.append("受控侧光/亮度统计不能替代真实强逆光证据")
        if required_scene == "low_light" and not item.get("low_light_confirmed"):
            reasons.append("缺少真实低照度采集证据")
    if stats.get("known", 0) < 100 or stats.get("known_subjects", 0) < 10:
        reasons.append("样本不足：至少需 100 次已知查询及 10 名已知人员")
    if reasons:
        status = (
            "探索性结果，不能判定达标"
            if not real_capture or not independent_calibration
            else "已有实测，目标场景证据不足"
        )
    elif rate < target:
        status = "未达到目标"
    elif (
        stats.get("confirmation_ci95")
        and stats["confirmation_ci95"][0] >= target
        and stats.get("confirmation_subject_bootstrap_ci95")
        and stats["confirmation_subject_bootstrap_ci95"][0] >= target
    ):
        status = "达到目标（仅本测试协议，95%区间下限通过）"
    else:
        status = "点估计达到目标，95%区间下限不足"
    return {
        "target": target,
        "observed": rate,
        "status": status,
        "reasons": list(dict.fromkeys(reasons)),
        "ci95": stats.get("confirmation_ci95"),
        "subject_ci95": stats.get("confirmation_subject_bootstrap_ci95"),
    }
