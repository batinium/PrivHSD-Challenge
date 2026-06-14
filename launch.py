#!/usr/bin/env python3
"""Launch the local ContextSafe-HSD privacy review workbench."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
STARTUP_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 5.0
DEFAULT_MICROMAMBA_ENV = "contextsafe-hsd"


@dataclass(frozen=True)
class PortProcess:
    pid: int
    cmdline: tuple[str, ...]
    cwd: Path | None


def active_environment_name() -> str | None:
    return os.environ.get("CONDA_DEFAULT_ENV") or os.environ.get("MAMBA_DEFAULT_ENV")


def python_command() -> list[str]:
    override = os.environ.get("CONTEXTSAFE_HSD_PYTHON")
    if override:
        return [override]

    env_name = os.environ.get("CONTEXTSAFE_HSD_ENV", DEFAULT_MICROMAMBA_ENV)
    if active_environment_name() == env_name:
        return [sys.executable]

    active_prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("MAMBA_PREFIX")
    if active_prefix and Path(active_prefix).name == env_name:
        return [sys.executable]

    micromamba = shutil.which("micromamba")
    if micromamba:
        return [micromamba, "run", "-n", env_name, "python"]

    raise SystemExit(
        "micromamba is required to launch outside the active contextsafe-hsd "
        "environment. Install micromamba, activate contextsafe-hsd, or set "
        "CONTEXTSAFE_HSD_PYTHON to an explicit Python executable."
    )


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def local_connect_host(host: str) -> str:
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def listening_socket_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    expected_port = f"{port:04X}"
    for path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10:
                continue
            local_address = fields[1]
            state = fields[3]
            inode = fields[9]
            try:
                _address, raw_port = local_address.rsplit(":", 1)
            except ValueError:
                continue
            if raw_port.upper() == expected_port and state == "0A":
                inodes.add(inode)
    return inodes


def process_cmdline(pid: int) -> tuple[str, ...]:
    try:
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ()
    return tuple(part.decode("utf-8", "replace") for part in raw.split(b"\0") if part)


def process_cwd(pid: int) -> Path | None:
    try:
        return Path(os.readlink(Path("/proc") / str(pid) / "cwd")).resolve()
    except OSError:
        return None


def processes_for_port(port: int) -> list[PortProcess]:
    inodes = listening_socket_inodes(port)
    if not inodes:
        return []
    processes: list[PortProcess] = []
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []
    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdigit():
            continue
        fd_dir = proc_dir / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        owns_socket = False
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                owns_socket = True
                break
        if owns_socket:
            pid = int(proc_dir.name)
            processes.append(
                PortProcess(
                    pid=pid,
                    cmdline=process_cmdline(pid),
                    cwd=process_cwd(pid),
                )
            )
    return processes


def is_workbench_process(process: PortProcess) -> bool:
    command = " ".join(process.cmdline)
    cwd = process.cwd.resolve() if process.cwd else None
    in_repo = cwd is not None and (cwd == ROOT or ROOT in cwd.parents)
    in_frontend = cwd is not None and (
        cwd == FRONTEND_DIR or FRONTEND_DIR in cwd.parents
    )
    backend = "uvicorn" in command and "workbench.backend.app:app" in command
    frontend = "vite" in command and (
        in_frontend or str(FRONTEND_DIR) in command or "contextsafe-hsd-workbench" in command
    )
    return (backend and in_repo) or frontend


def describe_process(process: PortProcess) -> str:
    command = " ".join(process.cmdline) if process.cmdline else "<unknown>"
    cwd = str(process.cwd) if process.cwd else "<unknown cwd>"
    return f"pid {process.pid} ({command}; cwd={cwd})"


def terminate_process_group(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    if pgid == os.getpgrp():
        return
    os.killpg(pgid, signal.SIGTERM)


def kill_stale_workbench_processes(port: int, *, label: str) -> None:
    owners = processes_for_port(port)
    if not owners:
        return
    stale = [process for process in owners if is_workbench_process(process)]
    if not stale:
        owner_text = "; ".join(describe_process(process) for process in owners)
        raise SystemExit(
            f"{label} port is already in use by a non-workbench process: {owner_text}"
        )
    for process in stale:
        print(f"Stopping stale {label.lower()} process on port {port}: {describe_process(process)}")
        try:
            terminate_process_group(process.pid)
        except PermissionError as exc:
            raise SystemExit(
                f"Cannot stop stale {label.lower()} process {process.pid}: {exc}"
            ) from exc
    deadline = time.time() + SHUTDOWN_TIMEOUT_SECONDS
    while time.time() < deadline:
        if not port_is_open("127.0.0.1", port):
            return
        time.sleep(0.1)
    for process in stale:
        if process_exists(process.pid):
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    deadline = time.time() + SHUTDOWN_TIMEOUT_SECONDS
    while time.time() < deadline:
        if not port_is_open("127.0.0.1", port):
            return
        time.sleep(0.1)
    raise SystemExit(f"{label} port is still in use after stopping stale processes: {port}")


def run_checked(command: list[str], *, cwd: Path) -> None:
    print(f"$ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def ensure_backend_deps(python: list[str], *, install: bool) -> None:
    check = subprocess.run(
        [
            *python,
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
            "  micromamba env update -n contextsafe-hsd -f environment.yml\n"
            "or:\n"
            "  micromamba run -n contextsafe-hsd -e PYTHONNOUSERSITE=1 python launch.py --install"
        )
    run_checked(
        [*python, "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
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
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        start_new_session=True,
        text=True,
    )
    print(f"{name} started with pid {process.pid}")
    return process


def wait_for_port(
    *,
    host: str,
    port: int,
    name: str,
    processes: list[subprocess.Popen[str]],
) -> None:
    connect_host = local_connect_host(host)
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        for process in processes:
            returncode = process.poll()
            if returncode is not None:
                raise RuntimeError(
                    f"{name} did not start because process {process.pid} "
                    f"exited with status {returncode}."
                )
        if port_is_open(connect_host, port):
            return
        time.sleep(0.25)
    raise TimeoutError(
        f"{name} did not open {connect_host}:{port} "
        f"within {STARTUP_TIMEOUT_SECONDS:.0f}s."
    )


def terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.time() + SHUTDOWN_TIMEOUT_SECONDS
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
    parser.add_argument(
        "--no-kill-existing",
        action="store_true",
        help=(
            "Do not stop stale workbench processes already listening on the "
            "configured ports."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("PYTHONNOUSERSITE", "1")
    python = python_command()
    ensure_backend_deps(python, install=args.install)
    ensure_frontend_deps(install=args.install)

    if not args.no_kill_existing:
        kill_stale_workbench_processes(args.backend_port, label="Backend")
        kill_stale_workbench_processes(args.frontend_port, label="Frontend")

    connect_host = local_connect_host(args.host)
    if port_is_open(connect_host, args.backend_port):
        raise SystemExit(f"Backend port already in use: {args.host}:{args.backend_port}")
    if port_is_open(connect_host, args.frontend_port):
        raise SystemExit(f"Frontend port already in use: {args.host}:{args.frontend_port}")

    backend_command = [
        *python,
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
        "--strictPort",
    ]
    backend_target = f"http://{local_connect_host(args.host)}:{args.backend_port}"

    processes: list[subprocess.Popen[str]] = []
    try:
        processes.append(start_process(backend_command, cwd=ROOT, name="backend"))
        processes.append(
            start_process(
                frontend_command,
                cwd=FRONTEND_DIR,
                name="frontend",
                extra_env={"VITE_BACKEND_TARGET": backend_target},
            )
        )
        wait_for_port(
            host=args.host,
            port=args.backend_port,
            name="Backend",
            processes=processes,
        )
        wait_for_port(
            host=args.host,
            port=args.frontend_port,
            name="Frontend",
            processes=processes,
        )
        print()
        print(f"Workbench: http://{args.host}:{args.frontend_port}")
        print(f"Backend:   http://{args.host}:{args.backend_port}")
        print(f"API proxy: {backend_target}")
        print("Press Ctrl+C to stop both servers.")
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except (RuntimeError, TimeoutError) as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopping workbench...")
    finally:
        terminate(processes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
