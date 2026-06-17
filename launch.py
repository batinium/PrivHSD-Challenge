#!/usr/bin/env python3
"""Launch the local backend API and Expo frontend."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
MOBILE_DIR = ROOT / "mobile"
DEFAULT_BACKEND_PORT = 8765
DEFAULT_EXPO_PORT = 8081


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch ContextSafe backend API and Expo frontend.",
    )
    parser.add_argument(
        "--target",
        choices=["android", "android-auto", "web", "metro"],
        default="android",
        help=(
            "Frontend target. android starts Metro for a Windows/WSL emulator; "
            "android-auto also asks Expo to open an emulator using a Linux SDK."
        ),
    )
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--expo-port", type=int, default=DEFAULT_EXPO_PORT)
    parser.add_argument(
        "--expo-host",
        choices=["lan", "localhost", "tunnel"],
        default=None,
        help="Optional Expo host mode. Use tunnel if the Windows emulator cannot reach WSL.",
    )
    parser.add_argument("--skip-backend", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    return parser


def run_checked(command: list[str], *, cwd: Path) -> None:
    print(f"[launch] {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def npm_install_if_needed(skip_install: bool) -> None:
    if skip_install:
        return
    if (MOBILE_DIR / "node_modules").exists():
        return
    run_checked(["npm", "install"], cwd=MOBILE_DIR)


def backend_public_url(target: str, host: str, port: int) -> str:
    if target in {"android", "android-auto"}:
        return f"http://10.0.2.2:{port}"
    if host in {"127.0.0.1", "0.0.0.0"}:
        return f"http://localhost:{port}"
    return f"http://{host}:{port}"


def start_backend(host: str, port: int) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "contextsafe_hsd.api_server",
        "--host",
        host,
        "--port",
        str(port),
    ]
    print(f"[launch] starting backend: {' '.join(command)}")
    return subprocess.Popen(command, cwd=ROOT, text=True)


def wait_for_backend(host: str, port: int, timeout_seconds: float = 15.0) -> None:
    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    print(f"[launch] backend ready: {url}")
                    return
        except URLError:
            time.sleep(0.25)
    raise RuntimeError(f"backend did not become ready: {url}")


def expo_command(target: str, port: int, host_mode: str | None) -> list[str]:
    command = ["npx", "expo", "start", "--port", str(port)]
    if host_mode is not None:
        command.extend(["--host", host_mode])
    if target == "android-auto":
        command.append("--android")
    elif target == "web":
        command.append("--web")
    return command


def terminate(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not MOBILE_DIR.exists():
        raise SystemExit("mobile/ does not exist. Run from the repo root.")

    npm_install_if_needed(args.skip_install)

    backend_process: subprocess.Popen[str] | None = None
    if not args.skip_backend:
        backend_process = start_backend(args.backend_host, args.backend_port)
        wait_for_backend(args.backend_host, args.backend_port)

    api_url = backend_public_url(args.target, args.backend_host, args.backend_port)
    env = os.environ.copy()
    env["EXPO_PUBLIC_API_BASE_URL"] = api_url

    command = expo_command(args.target, args.expo_port, args.expo_host)
    print(f"[launch] frontend API URL: {api_url}")
    print(f"[launch] starting frontend: {' '.join(command)}")
    try:
        return subprocess.call(command, cwd=MOBILE_DIR, env=env)
    finally:
        terminate(backend_process)


if __name__ == "__main__":
    raise SystemExit(main())
