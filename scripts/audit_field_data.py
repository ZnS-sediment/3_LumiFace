#!/usr/bin/env python3
"""Audit self-collected field data and optionally export application-ready query ZIPs.
Reads independent manual bbox labels; never creates labels from the tested model.
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def query_shards(rows, blobs, max_bytes=90 * 1024 * 1024, max_label_bytes=1024 * 1024):
    """Reserve headroom for ZIP/manifest overhead below the application's limits."""
    chunk = []
    image_bytes = label_bytes = 0
    for row in rows:
        size = len(blobs[row["file"]])
        labels = len(json.dumps(row, ensure_ascii=False).encode())
        if size > max_bytes or labels > max_label_bytes:
            raise ValueError("单张图片或标注超过导出分包限制")
        if chunk and (
            len(chunk) >= 500
            or image_bytes + size > max_bytes
            or label_bytes + labels > max_label_bytes
        ):
            yield chunk
            chunk = []
            image_bytes = label_bytes = 0
        chunk.append(row)
        image_bytes += size
        label_bytes += labels
    if chunk:
        yield chunk


def audit(config_path: Path, output: Path, export: bool = False) -> dict:
    from app.core.config import MAX_UPLOAD
    from app.schemas.contracts import Manifest, DatasetItem, ResearchProtocol
    from app.services.images import decode, digest, png

    config = json.loads(config_path.read_text())
    base = config_path.resolve().parent
    protocol = ResearchProtocol.model_validate(config.get("protocol", {}))
    roles = defaultdict(list)
    hashes = {}
    session_roles = defaultdict(set)
    unknowns = defaultdict(set)
    counts = defaultdict(
        lambda: {"images": 0, "known": 0, "unknown": 0, "subjects": set(), "known_subjects": set()}
    )
    errors = []
    blobs = {}
    identity_subjects = defaultdict(set)
    subject_identities = defaultdict(set)
    for key in ("name", "source", "license"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            errors.append(f"缺少 {key} 描述")
    for index, row in enumerate(config.get("images", [])):
        role = row.get("role")
        if role not in ("gallery", "calibration", "test"):
            errors.append(f"images[{index}]: role 须为 gallery/calibration/test")
            continue
        try:
            path = (base / row["file"]).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise ValueError("缺失文件或路径越界")
            image = decode(path.read_bytes())
            encoded = png(image)
            if len(encoded) > MAX_UPLOAD:
                raise ValueError("无损 PNG 超过导入的 12 MB 单图限制，请先裁剪或缩小并同步修正标注")
            value = DatasetItem.model_validate(
                {k: row[k] for k in ["file", "scene", "capture_id", "faces"]}
            )
            if any(f.bbox[2] > image.shape[1] or f.bbox[3] > image.shape[0] for f in value.faces):
                raise ValueError("bbox 超出 EXIF 纠正后的图像尺寸")
            if role == "gallery" and (len(value.faces) != 1 or value.faces[0].person_id is None):
                raise ValueError("gallery 每图须有一个已注册身份标签")
            fingerprint = digest(image)
            if fingerprint in hashes:
                errors.append(f"images[{index}]: 与 {hashes[fingerprint]} 像素重复")
            hashes[fingerprint] = row["file"]
            session_roles[value.capture_id].add(role)
            roles[role].append(value.model_dump())
            blobs[row["file"]] = encoded
            for face in value.faces:
                subject_identities[face.subject].add(face.person_id)
                if face.person_id is not None:
                    identity_subjects[face.person_id].add(face.subject)
            if role != "gallery":
                stats = counts[(role, value.scene)]
                stats["images"] += 1
                for face in value.faces:
                    stats["known" if face.person_id is not None else "unknown"] += 1
                    stats["subjects"].add(face.subject)
                    if face.person_id is not None:
                        stats["known_subjects"].add(face.subject)
                    if face.person_id is None:
                        unknowns[role].add(face.subject)
        except Exception as exc:
            errors.append(f"images[{index}]: {exc}")
    for session, found in session_roles.items():
        if len(found) > 1:
            errors.append(f"采集会话跨划分：{session} -> {sorted(found)}")
    if unknowns["calibration"] & unknowns["test"]:
        errors.append("校准与测试未知身份重叠")
    if any(len(labels) > 1 for labels in identity_subjects.values()):
        errors.append("同一 person_id 使用多个 subject 标识，可能虚增人员数")
    if any(len(identities) > 1 for identities in subject_identities.values()):
        errors.append("同一 subject 对应不同已知/未知身份标签")
    gallery_ids = {f["person_id"] for row in roles["gallery"] for f in row["faces"]}
    for role in ("calibration", "test"):
        for row in roles[role]:
            if any(
                f["person_id"] is not None and f["person_id"] not in gallery_ids
                for f in row["faces"]
            ):
                errors.append(f"{role} 查询引用无参考样本的已知身份：{row['file']}")
    gaps = []
    for scene in ["normal", "low_light", "backlight", "infrared"]:
        for role in ["calibration", "test"]:
            stats = counts[(role, scene)]
            if stats["known"] < 100 or len(stats["known_subjects"]) < 10:
                gaps.append(
                    {
                        "split": role,
                        "scene": scene,
                        "known_faces": stats["known"],
                        "known_subjects": len(stats["known_subjects"]),
                        "recommendation": "至少 100 次已知查询和 10 名受试者；正式实训建议 20 人以上、多会话独立采集",
                    }
                )
    if not roles["gallery"]:
        errors.append("缺少图库参考照片")
    if not unknowns["calibration"] or not unknowns["test"]:
        errors.append("校准和测试均须包含互斥的未知身份")
    if protocol.capture_independence != "session_disjoint":
        errors.append("目标验收需要 session_disjoint 协议声明与会话日志")
    for scene in ["normal", "infrared", "backlight", "low_light"]:
        evidence = protocol.scene_evidence.get(scene)
        if (
            evidence is None
            or not evidence.source
            or evidence.annotation_basis != "manual_capture_log"
        ):
            errors.append(f"{scene} 缺少人工采集日志证据")
        elif scene == "infrared" and not (
            evidence.modality == "nir" and evidence.active_illumination and evidence.night_confirmed
        ):
            errors.append("infrared 须证明近红外、主动补光和夜间条件")
        elif scene == "backlight" and not evidence.backlight_confirmed:
            errors.append("缺少真实强逆光证据")
        elif scene == "low_light" and not evidence.low_light_confirmed:
            errors.append("缺少真实低照度证据")
    report = {
        "source": str(config_path.resolve()),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "roles": {role: len(rows) for role, rows in roles.items()},
        "errors": list(dict.fromkeys(errors)),
        "coverage_gaps": gaps,
        "ready_for_target_assessment": not errors and not gaps,
        "note": "采集场景声明须由实验负责人核实；软件无法从像素证明夜间、设备波段或照明位置。",
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    (output / "field-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if export:
        if errors:
            raise ValueError("审计未通过，未导出 ZIP。请查看 field-audit.json")
        for role in ["calibration", "test"]:
            # Application limits remain in force; shard without changing subjects or sessions.
            for part, rows in enumerate(query_shards(roles[role], blobs), 1):
                manifest = Manifest(
                    name=f"{config['name']}-{role}-{part}",
                    split=role,
                    source=config["source"],
                    license=config["license"],
                    real_capture=True,
                    protocol=protocol,
                    items=rows,
                )
                destination = output / f"{role}-{part}.zip"
                with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as package:
                    package.writestr("manifest.json", manifest.model_dump_json())
                    for item in rows:
                        package.writestr(item["file"], blobs[item["file"]])
                destination.chmod(0o600)
        (output / "gallery-registration-plan.json").write_text(
            json.dumps(roles["gallery"], ensure_ascii=False, indent=2)
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "work/field-study-audit")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    report = audit(args.config, args.output, args.export)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ready_for_target_assessment"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
