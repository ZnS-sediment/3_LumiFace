#!/usr/bin/env python3
"""Register one new identity per folder through the running local LumiFace API.
Default: offline preflight only. --apply explicitly registers identities.
"""

import argparse
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_IMAGE = 12 * 1024 * 1024


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def local_api(value):
    url = urllib.parse.urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname not in ("localhost", "127.0.0.1", "::1")
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise argparse.ArgumentTypeError("--api 必须是本机 HTTP 根地址，例如 http://127.0.0.1:8000")
    return value.rstrip("/")


def plan_import(root, capture_prefix):
    if not root.is_dir():
        raise ValueError("照片根目录不存在")
    root = root.resolve()
    plans = []
    errors = []
    directories = sorted(
        (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name,
    )
    if not directories:
        raise ValueError("根目录中没有人员子文件夹；每个人应单独放一个文件夹")
    for folder in directories:
        prefix = f"{folder.name}: "
        if folder.is_symlink():
            errors.append(prefix + "不接受符号链接文件夹")
            continue
        name = folder.name.strip()
        capture_id = f"{capture_prefix}:{folder.name}"
        if not 1 <= len(name) <= 80:
            errors.append(prefix + "文件夹名称须为 1–80 字")
        if not 1 <= len(capture_id) <= 120:
            errors.append(prefix + "采集前缀与人员名合计超过 120 字")
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS),
            key=lambda p: p.name,
        )
        if not 1 <= len(files) <= 10:
            errors.append(prefix + "每人须有 1–10 张 JPG/PNG，不支持嵌套文件夹")
        if any(p.is_dir() for p in folder.iterdir()):
            errors.append(prefix + "请将该人员的照片直接放在人员目录下")
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                errors.append(prefix + "不接受越界或符号链接照片")
            elif not 0 < path.stat().st_size <= MAX_IMAGE:
                errors.append(prefix + path.name + " 为空或超过 12 MB")
        plans.append({"name": name, "capture_id": capture_id, "files": files})
    if len({p["name"] for p in plans}) != len(plans):
        errors.append("去掉首尾空格后人员名称重复")
    if errors:
        raise ValueError("\n".join(errors))
    return plans


def request_json(api, path, timeout, body=None, content_type=None):
    headers = {"Content-Type": content_type} if content_type else {}
    req = urllib.request.Request(api + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            error = json.loads(raw)
            message = error.get("message") or error.get("detail") or raw
        except json.JSONDecodeError:
            message = raw
        raise APIError(exc.code, str(message)) from exc


def multipart(plan, note):
    boundary = "LumiFace" + uuid.uuid4().hex
    chunks = []
    for key, value in [("name", plan["name"]), ("note", note), ("capture_id", plan["capture_id"])]:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        )
        chunks.append(value.encode("utf-8") + b"\r\n")
    for index, path in enumerate(plan["files"]):
        content = path.read_bytes()
        if not 0 < len(content) <= MAX_IMAGE:
            raise ValueError(f"照片在预检后发生变化：{path.name}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        # Only ASCII generated filenames appear in multipart headers; original names stay local.
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="photo-{index}{path.suffix.lower()}"\r\nContent-Type: {mime}\r\n\r\n'
            ).encode()
        )
        chunks.extend([content, b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def save_report(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(
        description="每人一个文件夹的本机人脸身份批量注册；默认只预检。"
    )
    parser.add_argument("folder", type=Path, help="人员照片根目录")
    parser.add_argument(
        "--capture-prefix",
        required=True,
        help="实际注册照片的采集会话，例如 enroll-20261017-morning",
    )
    parser.add_argument("--api", type=local_api, default="http://127.0.0.1:8000")
    parser.add_argument("--note", default="批量注册", help="所有本批人员的备注")
    parser.add_argument("--timeout", type=float, default=300, help="每个 HTTP 请求超时秒数")
    parser.add_argument(
        "--report", type=Path, help="导入报告路径；默认在当前目录使用带时间戳的文件名"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--apply", action="store_true", help="实际向身份库写入；同名人员跳过，不追加或覆盖"
    )
    modes.add_argument("--dry-run", action="store_true", help="仅离线检查文件；默认行为")
    args = parser.parse_args()
    if not args.capture_prefix.strip() or len(args.note) > 500 or args.timeout <= 0:
        parser.error("采集前缀不能为空，备注最多 500 字，超时须大于 0")
    try:
        plans = plan_import(args.folder, args.capture_prefix)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    for plan in plans:
        print(f"[待导入] {plan['name']}：{len(plan['files'])} 张，采集编号 {plan['capture_id']}")
    print(f"共 {len(plans)} 人，{sum(len(p['files']) for p in plans)} 张照片。")
    if not args.apply:
        print(
            "预检完成，未连接服务、未写入身份库。预检不判断照片中是否有人脸；实际注册时由后端检测。确认后添加 --apply。"
        )
        return 0
    try:
        existing = {p["name"] for p in request_json(args.api, "/api/person", args.timeout)}
    except (APIError, urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        print(f"无法读取身份库，尚未注册任何人员：{exc}", file=sys.stderr)
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.report or Path(f"face-import-{stamp}.json")
    report = {
        "api": args.api,
        "started_at_utc": stamp,
        "planned": len(plans),
        "results": [],
        "completed": False,
    }
    for plan in plans:
        row = {"name": plan["name"], "capture_id": plan["capture_id"], "photos": len(plan["files"])}
        if plan["name"] in existing:
            row.update(status="skipped", reason="身份库已有同名人员；未覆盖或追加照片")
        else:
            try:
                body, content_type = multipart(plan, args.note)
                person = request_json(
                    args.api, "/api/person/register", args.timeout, body, content_type
                )
                row.update(
                    status="registered", person_id=person["id"], sample_count=person["sample_count"]
                )
                existing.add(plan["name"])
            except APIError as exc:
                row.update(
                    status="failed" if exc.status < 500 else "uncertain",
                    http_status=exc.status,
                    reason=str(exc),
                )
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                row.update(
                    status="uncertain",
                    reason=f"连接中断或超时，可能已提交；请先到页面核对，不自动重试：{exc}",
                )
            except (OSError, ValueError, KeyError) as exc:
                row.update(
                    status="uncertain", reason=f"文件或响应异常，请核对身份库后再操作：{exc}"
                )
        report["results"].append(row)
        save_report(destination, report)
        print(
            f"[{row['status']}] {row['name']}：{row.get('reason', '编号 ' + str(row.get('person_id')))}",
            flush=True,
        )
        if row["status"] == "uncertain":
            print("已停止后续注册。前面已成功的身份会保留，请查看报告并核对页面。", file=sys.stderr)
            return 1
    report["completed"] = True
    report["counts"] = {
        status: sum(r["status"] == status for r in report["results"])
        for status in ["registered", "skipped", "failed"]
    }
    save_report(destination, report)
    print(
        "导入结果："
        + json.dumps(report["counts"], ensure_ascii=False)
        + "；报告 "
        + str(destination.resolve())
    )
    return 1 if report["counts"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
