#!/usr/bin/env python3
"""Launch the local ContextSafe-HSD privacy review workbench."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "workbench" / "frontend"
BACKEND_REQUIREMENTS = ROOT / "workbench" / "backend" / "requirements.txt"


def venv_python() -> Path:
    candidates = [
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def run_checked(command: list[str], *, cwd: Path) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def ensure_backend_deps(python: Path, *, install: bool) -> None:
    check = subprocess.run(
        [
            str(python),
            "-c",
            "import fastapi, uvicorn",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode == 0:
        return
    if not install:
        raise SystemExit(
            "FastAPI backend dependencies are missing. Run:\n"
            "  python launch.py --install\n"
            "or:\n"
            "  .venv/bin/python -m pip install -r workbench/backend/requirements.txt"
        )
    run_checked(
        [str(python), "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
        cwd=ROOT,
    )


def ensure_frontend_deps(*, install: bool) -> None:
    if shutil.which("npm") is None:
        raise SystemExit("npm is required to launch the React frontend.")
    if (FRONTEND_DIR / "node_modules").exists():
        return
    if not install:
        raise SystemExit(
            "Frontend dependencies are missing. Run:\n"
            "  python launch.py --install\n"
            "or:\n"
            "  cd workbench/frontend && npm install"
        )
    run_checked(["npm", "install"], cwd=FRONTEND_DIR)


def start_process(
    command: list[str],
    *,
    cwd: Path,
    name: str,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        start_new_session=True,
        text=True,
    )
    print(f"{name} started with pid {process.pid}")
    return process


def terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.time() + 5
    for process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the FastAPI backend and React frontend workbench.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install missing backend and frontend dependencies before launch.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable FastAPI reload mode for backend development.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python = venv_python()
    ensure_backend_deps(python, install=args.install)
    ensure_frontend_deps(install=args.install)

    if port_is_open(args.host, args.backend_port):
        raise SystemExit(f"Backend port already in use: {args.host}:{args.backend_port}")
    if port_is_open(args.host, args.frontend_port):
        raise SystemExit(f"Frontend port already in use: {args.host}:{args.frontend_port}")

    backend_command = [
        str(python),
        "-m",
        "uvicorn",
        "workbench.backend.app:app",
        "--host",
        args.host,
        "--port",
        str(args.backend_port),
    ]
    if args.reload:
        backend_command.append("--reload")

    frontend_command = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        args.host,
        "--port",
        str(args.frontend_port),
    ]

    processes: list[subprocess.Popen[str]] = []
    try:
        processes.append(start_process(backend_command, cwd=ROOT, name="backend"))
        processes.append(start_process(frontend_command, cwd=FRONTEND_DIR, name="frontend"))
        print()
        print(f"Workbench: http://{args.host}:{args.frontend_port}")
        print(f"Backend:   http://{args.host}:{args.backend_port}")
        print("Press Ctrl+C to stop both servers.")
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping workbench...")
    finally:
        terminate(processes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
