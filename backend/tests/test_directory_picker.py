"""Native selection is explicit, bounded, and never resolves request-supplied paths."""

import base64
import subprocess
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import directory_picker as picker


@pytest.fixture
def selected(monkeypatch, tmp_path):
    root = tmp_path / "gallery"
    person = root / "人员 001"
    person.mkdir(parents=True)
    (person / "01.png").write_bytes(b"first-photo")
    (person / "02.JPG").write_bytes(b"second-photo")
    (root / "README.txt").write_text("not a photo")
    display = r"C:\Users\演示\Downloads\gallery"
    monkeypatch.setattr(picker, "available", lambda: True)
    monkeypatch.setattr(picker, "_executable", lambda: "DirectoryPicker.exe")
    monkeypatch.setattr(picker, "_show_dialog", lambda _: display)
    monkeypatch.setattr(picker, "_local_directory", lambda _: root)
    return root, display


def test_selection_returns_full_path_and_exact_photos_without_writing_sources(client, selected):
    root, display = selected
    assert client.get("/api/system/directory-picker").json()["data"]["available"]
    response = client.post("/api/system/directory-picker", headers={"X-LumiFace-Picker": "1"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["path"] == display
    assert [(item["path"], item["type"]) for item in data["files"]] == [
        ("gallery/人员 001/01.png", "image/png"),
        ("gallery/人员 001/02.JPG", "image/jpeg"),
    ]
    assert all("content" not in item for item in data["files"])
    assert [client.get(item["url"]).content for item in data["files"]] == [
        b"first-photo",
        b"second-photo",
    ]
    assert [item["size"] for item in data["files"]] == [11, 12]
    assert (root / "人员 001/01.png").read_bytes() == b"first-photo"
    assert client.get("/api/person").json()["data"] == []


def test_selection_requires_application_header_and_ignores_paths_in_body(client, selected):
    assert client.post("/api/system/directory-picker").status_code == 403
    response = client.post(
        "/api/system/directory-picker",
        headers={"X-LumiFace-Picker": "1"},
        json={"path": "/etc", "command": "not executable"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["path"] == selected[1]


def test_unsupported_and_cancel_do_not_read_directories(client, monkeypatch):
    monkeypatch.setattr(picker, "available", lambda: False)
    assert not client.get("/api/system/directory-picker").json()["data"]["available"]
    assert (
        client.post("/api/system/directory-picker", headers={"X-LumiFace-Picker": "1"}).status_code
        == 503
    )
    monkeypatch.setattr(picker, "available", lambda: True)
    monkeypatch.setattr(picker, "_executable", lambda: "DirectoryPicker.exe")
    monkeypatch.setattr(picker, "_show_dialog", lambda _: None)
    monkeypatch.setattr(picker, "_local_directory", lambda _: pytest.fail("cancel must not read"))
    assert (
        client.post("/api/system/directory-picker", headers={"X-LumiFace-Picker": "1"}).json()[
            "data"
        ]
        is None
    )


def test_busy_and_timeout_release_picker_for_retry(monkeypatch, selected):
    with picker._picker_lock:
        with pytest.raises(AppError) as caught:
            picker.choose()
        assert caught.value.status == 409

    def timeout(_):
        raise subprocess.TimeoutExpired("powershell.exe", 300)

    monkeypatch.setattr(picker, "_show_dialog", timeout)
    with pytest.raises(AppError) as caught:
        picker.choose()
    assert caught.value.status == 408
    monkeypatch.setattr(picker, "_show_dialog", lambda _: None)
    assert picker.choose() is None


@pytest.mark.parametrize("kind", ["flat", "nested", "symlink", "count", "size", "total", "empty"])
def test_invalid_photo_roots_fail_before_returning_content(selected, tmp_path, monkeypatch, kind):
    root, _ = selected
    if kind == "flat":
        (root / "bad.png").write_bytes(b"photo")
    elif kind == "nested":
        (root / "人员 001/nested").mkdir()
    elif kind == "symlink":
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"outside")
        (root / "人员 001/link.png").symlink_to(outside)
    elif kind == "count":
        for index in range(11):
            (root / "人员 001" / f"{index}.png").write_bytes(b"photo")
    elif kind == "size":
        (root / "人员 001/empty.png").write_bytes(b"")
    elif kind == "total":
        monkeypatch.setattr(picker, "_MAX_TOTAL", 8)
    else:
        for item in (root / "人员 001").iterdir():
            item.unlink()
    with pytest.raises(AppError):
        picker.choose()
    assert not picker._picker_lock.locked()


def test_native_helper_command_and_separate_wsl_path_argument(monkeypatch, tmp_path):
    from pathlib import Path

    calls = []
    display = r"\\wsl.localhost\Ubuntu-20.04\home\路径有空格\gallery"

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "DirectoryPicker.exe":
            Path(args[1]).write_bytes(base64.b64encode(display.encode("utf-8")))
            return SimpleNamespace(stdout=b"")
        return SimpleNamespace(stdout=str(tmp_path).encode())

    monkeypatch.setattr(picker.subprocess, "run", run)
    monkeypatch.setattr(picker, "_windows_path", str)
    monkeypatch.setattr(picker, "DATA", tmp_path)
    assert picker._show_dialog("DirectoryPicker.exe") == display
    assert calls[0][0][0] == "DirectoryPicker.exe" and len(calls[0][0]) == 2
    assert not Path(calls[0][0][1]).exists()  # Temporary result is always removed.
    assert "shell" not in calls[0][1]
    assert picker._local_directory(display) == tmp_path
    assert calls[1][0] == ["/usr/bin/wslpath", "-u", display]


def test_cancel_and_failed_native_process_remove_result_files(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.setattr(picker, "DATA", tmp_path)
    monkeypatch.setattr(picker, "_windows_path", str)

    def cancel(args, **kwargs):
        Path(args[1]).write_bytes(b"")

    monkeypatch.setattr(picker.subprocess, "run", cancel)
    assert picker._show_dialog("DirectoryPicker.exe") is None
    assert not list((tmp_path / "cache/directory-picker").iterdir())

    def fail(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(picker.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        picker._show_dialog("DirectoryPicker.exe")
    assert not list((tmp_path / "cache/directory-picker").iterdir())


def test_helper_is_compiled_once_and_rebuilt_only_when_source_changes(monkeypatch, tmp_path):
    source = tmp_path / "DirectoryPicker.cs"
    source.write_text("first build")
    manifest = tmp_path / "DirectoryPicker.manifest"
    manifest.write_text("first manifest")
    monkeypatch.setattr(picker, "_MANIFEST", manifest)
    monkeypatch.setattr(picker, "_SOURCE", source)
    monkeypatch.setattr(picker, "DATA", tmp_path)
    monkeypatch.setattr(picker, "_compiler", lambda: tmp_path / "csc.exe")
    monkeypatch.setattr(picker, "_windows_path", str)
    calls = []

    def compile(args, **kwargs):
        calls.append(args)
        output = next(arg[5:] for arg in args if arg.startswith("/out:"))
        from pathlib import Path

        Path(output).write_bytes(b"helper")
        return SimpleNamespace(stdout=b"")

    monkeypatch.setattr(picker.subprocess, "run", compile)
    first = picker._executable()
    assert picker._executable() == first and len(calls) == 1
    assert "/target:winexe" in calls[0]
    assert "/win32manifest:" + str(manifest) in calls[0]
    source.write_text("updated build")
    second = picker._executable()
    assert second != first and len(calls) == 2
    manifest.write_text("updated DPI declaration")
    assert picker._executable() != second and len(calls) == 3


def test_selection_never_reads_image_payloads_and_release_revokes_access(
    client, selected, monkeypatch
):
    from pathlib import Path

    original = Path.open

    def no_photo_reads(path, *args, **kwargs):
        if path.suffix.lower() in {".png", ".jpg"}:
            pytest.fail("selection must not open photo files")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_photo_reads)
    data = picker.choose()
    assert len(data["files"]) == 2
    assert client.delete("/api/system/directory-picker/" + data["token"]).status_code == 200
    assert client.get(data["files"][0]["url"]).status_code == 410
    assert client.get("/api/system/directory-picker/unknown/photos/0").status_code == 410


@pytest.mark.parametrize("change", ["bytes", "symlink", "parent_link", "removed", "expired"])
def test_lazy_reads_reject_changed_sources(client, selected, tmp_path, monkeypatch, change):
    root, _ = selected
    data = picker.choose()
    photo = root / "人员 001/01.png"
    if change == "bytes":
        photo.write_bytes(b"replacement-different-size")
    elif change == "symlink":
        photo.unlink()
        photo.symlink_to(root / "人员 001/02.JPG")
    elif change == "parent_link":
        person = root / "人员 001"
        moved = tmp_path / "moved"
        person.rename(moved)
        person.symlink_to(moved, target_is_directory=True)
    elif change == "removed":
        photo.unlink()
    else:
        monkeypatch.setattr(picker, "_SELECTION_TTL", -1)
    response = client.get(data["files"][0]["url"])
    assert response.status_code == (410 if change == "expired" else 409)


def test_lazy_preview_is_small_and_original_bytes_are_preserved(client, selected):
    from test_api import photo
    from PIL import Image
    import io

    root, _ = selected
    raw = photo(60)
    (root / "人员 001/01.png").write_bytes(raw)
    data = picker.choose()
    url = data["files"][0]["url"]
    response = client.get(url + "?preview=true")
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(response.content)).size) <= 96
    assert client.get(url).content == raw
    assert client.get(url.rsplit("/", 1)[0] + "/999").status_code == 404


def test_large_gallery_scans_400_people_and_enforces_500_limit(tmp_path):
    from app.services.directory_picker import _scan_photos
    from app.core.errors import AppError
    import pytest

    for index in range(400):
        person = tmp_path / f'person_{index:04}'
        person.mkdir()
        for photo in ('1.png', '2.png'):
            (person / photo).write_bytes(b'photo')
    assert len(_scan_photos(tmp_path)) == 800
    for index in range(400, 501):
        person = tmp_path / f'person_{index:04}'
        person.mkdir()
        (person / '1.png').write_bytes(b'photo')
    with pytest.raises(AppError, match='500'):
        _scan_photos(tmp_path)
