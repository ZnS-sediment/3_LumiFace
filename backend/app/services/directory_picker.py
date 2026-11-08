"""Read only the directory explicitly chosen in the local Windows system dialog."""

import base64
import hashlib
import logging
import os
from pathlib import Path
import subprocess
import threading
import tempfile
import secrets
import time
from dataclasses import dataclass

from app.core.config import DATA, ROOT, MAX_UPLOAD
from app.core.errors import AppError

_MAX_TOTAL = 100 * 1024 * 1024
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_picker_lock = threading.Lock()
_selection_lock = threading.Lock()
_SELECTION_TTL = 6 * 3600


@dataclass(frozen=True)
class SelectedPhoto:
    path: Path
    size: int
    modified: int
    inode: int


# Keep only metadata. Neither selection nor preview copies the source collection.
_selections: dict[str, tuple[float, Path, list[SelectedPhoto]]] = {}


_build_lock = threading.Lock()
_SOURCE = ROOT / "backend" / "native" / "DirectoryPicker.cs"
_MANIFEST = _SOURCE.with_suffix(".manifest")


def _compiler() -> Path | None:
    if os.environ.get("LUMIFACE_NATIVE_PICKER") == "0":
        return None
    if os.name == "nt":
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    elif Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists():
        windows = Path("/mnt/c/Windows")
    else:
        return None
    for framework in ("Framework64", "Framework"):
        path = windows / "Microsoft.NET" / framework / "v4.0.30319" / "csc.exe"
        if path.is_file():
            return path
    return None


def _windows_path(path: Path) -> str:
    if os.name == "nt":
        return str(path)
    return (
        subprocess.run(
            ["/usr/bin/wslpath", "-w", str(path)], capture_output=True, timeout=10, check=True
        )
        .stdout.decode("utf-8")
        .strip()
    )


def available() -> bool:
    return _SOURCE.is_file() and _MANIFEST.is_file() and _compiler() is not None


def _executable() -> str:
    compiler = _compiler()
    if compiler is None:
        raise AppError("当前环境不支持系统目录选择，请在本机 Windows/WSL 环境启动后端后重试", 503)
    version = hashlib.sha256(
        _SOURCE.read_bytes() + b"\0" + _MANIFEST.read_bytes()
    ).hexdigest()[:16]
    folder = DATA / "cache" / "directory-picker"
    executable = folder / ("DirectoryPicker-" + version + ".exe")
    with _build_lock:
        if not executable.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            temporary = executable.with_suffix(".building.exe")
            try:
                subprocess.run(
                    [
                        str(compiler),
                        "/nologo",
                        "/optimize+",
                        "/target:winexe",
                        "/win32manifest:" + _windows_path(_MANIFEST),
                        "/out:" + _windows_path(temporary),
                        _windows_path(_SOURCE),
                    ],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                temporary.replace(executable)
                executable.chmod(0o700)
            finally:
                temporary.unlink(missing_ok=True)
    return str(executable)


def prepare() -> None:
    """Compile once before interaction; repeated clicks only launch the small native helper."""
    if available():
        try:
            _executable()
        except (OSError, subprocess.SubprocessError, AppError):
            logging.exception("Cannot prepare the local directory picker")


def _show_dialog(executable: str) -> str | None:
    folder = DATA / "cache" / "directory-picker"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder, prefix="selection-") as temporary:
        output = Path(temporary) / "result.txt"
        subprocess.run(
            [executable, _windows_path(output)], capture_output=True, timeout=300, check=True
        )
        payload = output.read_bytes().strip()
        return base64.b64decode(payload, validate=True).decode("utf-8") if payload else None


def _local_directory(display_path: str) -> Path:
    if os.name == "nt":
        return Path(display_path).resolve(strict=True)
    converted = (
        subprocess.run(
            ["/usr/bin/wslpath", "-u", display_path],
            capture_output=True,
            timeout=10,
            check=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    return Path(converted).resolve(strict=True)


def _scan_photos(root: Path) -> list[SelectedPhoto]:
    if not root.is_dir():
        raise AppError("所选路径不是文件夹")
    photos: list[SelectedPhoto] = []
    people = 0
    total = 0
    # DirEntry reuses filesystem metadata, especially useful for Windows disks under WSL.
    with os.scandir(root) as entries:
        people_entries = sorted(entries, key=lambda entry: entry.name)
    for person in people_entries:
        if person.is_symlink():
            raise AppError("人员文件夹不能是链接，请选择实际照片目录")
        if not person.is_dir(follow_symlinks=False):
            if Path(person.name).suffix.lower() in _IMAGE_SUFFIXES:
                raise AppError("请选照片根目录，每个人的照片放在一个子文件夹中")
            continue
        person_photos = []
        with os.scandir(person.path) as entries:
            for photo in sorted(entries, key=lambda entry: entry.name):
                if photo.is_symlink():
                    raise AppError("照片不能是链接，请使用实际照片文件")
                if photo.is_dir(follow_symlinks=False):
                    raise AppError("照片目录层级过深，请按“根目录 / 人员姓名 / 照片”存放")
                if Path(photo.name).suffix.lower() not in _IMAGE_SUFFIXES:
                    continue
                if not photo.is_file(follow_symlinks=False):
                    raise AppError("照片必须是普通文件")
                stat = photo.stat(follow_symlinks=False)
                if not 0 < stat.st_size <= MAX_UPLOAD:
                    raise AppError(f"{person.name} / {photo.name} 为空或超过 12 MB")
                total += stat.st_size
                if total > _MAX_TOTAL:
                    raise AppError("所选照片合计超过 100 MB，请分成多个目录导入")
                person_photos.append(
                    SelectedPhoto(Path(photo.path), stat.st_size, stat.st_mtime_ns, stat.st_ino)
                )
                if len(person_photos) > 10:
                    raise AppError(f"{person.name} 每人最多 10 张照片")
        if person_photos:
            people += 1
            if people > 500:
                raise AppError("每次最多选择 500 人，请分目录导入")
            photos.extend(person_photos)
    if not photos:
        raise AppError("未找到 JPG/PNG，请选包含人员子文件夹的照片根目录")
    return photos


def _selection(root: Path, display: str) -> dict:
    photos = _scan_photos(root)
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _selection_lock:
        for old, (updated, _, _) in list(_selections.items()):
            if now - updated > _SELECTION_TTL:
                _selections.pop(old)
        while len(_selections) >= 16:
            _selections.pop(next(iter(_selections)))
        _selections[token] = (now, root, photos)
    return {
        "path": display,
        "token": token,
        "files": [
            {
                "path": "/".join((root.name, photo.path.parent.name, photo.path.name)),
                "size": photo.size,
                "url": f"/api/system/directory-picker/{token}/photos/{index}",
                "type": "image/png" if photo.path.suffix.lower() == ".png" else "image/jpeg",
            }
            for index, photo in enumerate(photos)
        ],
    }


def release(token: str) -> None:
    with _selection_lock:
        _selections.pop(token, None)


def read_photo(token: str, index: int) -> tuple[bytes, str]:
    with _selection_lock:
        selected = _selections.get(token)
        if selected is None or time.monotonic() - selected[0] > _SELECTION_TTL:
            _selections.pop(token, None)
            raise AppError("目录选择已过期，请重新选择照片根目录", 410)
        _, root, photos = selected
        if not 0 <= index < len(photos):
            raise AppError("照片不存在", 404)
        photo = photos[index]
        _selections[token] = (time.monotonic(), root, photos)
    try:
        # Recheck before reading: sources may have changed since the dialog was confirmed.
        if (
            root.resolve(strict=True) != root
            or photo.path.parent.is_symlink()
            or photo.path.is_symlink()
            or photo.path.resolve(strict=True) != photo.path
        ):
            raise AppError("照片路径发生变化，请重新选择目录", 409)
        with photo.path.open("rb") as source:
            stat = os.fstat(source.fileno())
            if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (
                photo.size,
                photo.modified,
                photo.inode,
            ):
                raise AppError("照片发生变化，请重新选择目录", 409)
            raw = source.read(MAX_UPLOAD + 1)
        if len(raw) != photo.size:
            raise AppError("照片发生变化，请重新选择目录", 409)
        return raw, "image/png" if photo.path.suffix.lower() == ".png" else "image/jpeg"
    except OSError as exc:
        raise AppError("无法读取照片，请检查文件是否移动或删除后重新选择目录", 409) from exc


def choose() -> dict | None:
    if not available():
        raise AppError("当前环境不支持系统目录选择，请在本机 Windows/WSL 环境启动后端后重试", 503)
    if not _picker_lock.acquire(blocking=False):
        raise AppError("已有文件夹选择窗口打开，请先完成或取消选择", 409)
    try:
        path = _show_dialog(_executable())
        if path is None:
            return None
        root = _local_directory(path)
        return _selection(root, path)
    except AppError:
        raise
    except subprocess.TimeoutExpired as exc:
        raise AppError("选择目录超时，请重新选择", 408) from exc
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
        raise AppError("无法打开或读取所选目录，请检查文件夹权限后重新选择", 400) from exc
    finally:
        _picker_lock.release()
