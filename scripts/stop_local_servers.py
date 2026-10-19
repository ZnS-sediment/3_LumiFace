#!/usr/bin/env python3
"""Stop only this checkout's Uvicorn/Vite servers, never benchmark or unrelated jobs."""

import os
from pathlib import Path
import signal
import socket
import time

ROOT = Path(__file__).resolve().parents[1]


def is_project_server(arguments: list[str], cwd: Path, root: Path = ROOT) -> bool:
    if cwd not in (root, root / "frontend"):
        return False
    backend = "app.main:app" in arguments and (
        "uvicorn" in arguments or any(Path(x).name == "uvicorn" for x in arguments)
    )
    frontend = (
        any(Path(x).name in ("vite", "vite.js") for x in arguments) and cwd == root / "frontend"
    )
    return backend or frontend


def listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    matched = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            cwd = (entry / "cwd").resolve(strict=True)
            arguments = [
                x.decode(errors="replace")
                for x in (entry / "cmdline").read_bytes().split(b"\0")
                if x
            ]
            if is_project_server(arguments, cwd):
                os.kill(int(entry.name), signal.SIGTERM)
                matched.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    for _ in range(50):
        if not any(listening(port) for port in (8000, 5173)):
            print(f"本项目默认端口已释放；已通知进程：{matched}")
            return
        time.sleep(0.2)
    raise SystemExit(
        "默认端口仍被占用；未终止无法核实属于本项目的进程。若从隔离工具运行，请在普通 WSL 终端执行 bash scripts/stop.sh。"
    )


if __name__ == "__main__":
    main()
