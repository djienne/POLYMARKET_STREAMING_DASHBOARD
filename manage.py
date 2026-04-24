#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent
FREQTRADE_ROOT = ROOT.parent
BOT_ROOT = FREQTRADE_ROOT / "BTC_pricer_15m"
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
RUNTIME_DIR = ROOT / "runtime"
LOG_DIR = ROOT / "logs"
TMP_DIR = ROOT / ".codex_tmp"
VPS_INFO_DIR = ROOT / "vps_infos"

BACKEND_PID = RUNTIME_DIR / "dashboard_backend.pid"
FRONTEND_PID = RUNTIME_DIR / "dashboard_frontend.pid"
BACKEND_PORT = 8799
FRONTEND_PORT = 5174

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class VpsProfile:
    name: str
    label: str
    host: str
    user: str
    directory: str
    key: Path


def log(message: str, *, prefix: str = "manage") -> None:
    print(f"[{prefix}] {message}", flush=True)


def ensure_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def run(
    args: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    capture: bool = True,
) -> CommandResult:
    text_args = [str(a) for a in args]
    completed = subprocess.run(
        text_args,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    result = CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{text_args[0]} failed with exit code {result.returncode}: {detail}")
    return result


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def pids_listening_on(port: int) -> list[int]:
    if os.name != "nt":
        return []
    result = run(["netstat.exe", "-ano", "-p", "tcp"], capture=True)
    if result.returncode != 0:
        return []
    pids: set[int] = set()
    needle = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        state = parts[3].upper()
        pid_text = parts[4]
        if local_addr.endswith(needle) and state == "LISTENING" and pid_text.isdigit():
            pids.add(int(pid_text))
    return sorted(pids)


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = run(["tasklist.exe", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture=True)
        return result.returncode == 0 and str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_pid(pid: int, name: str) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if os.name == "nt":
        run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], capture=True)
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    log(f"stopped {name} pid={pid}", prefix="stop")


def read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def write_pid(path: Path, pid: int) -> None:
    ensure_dirs()
    path.write_text(str(pid), encoding="ascii")


def stop_pid_file(path: Path, name: str) -> None:
    pid = read_pid(path)
    if pid is not None and is_pid_running(pid):
        kill_pid(pid, name)
    try:
        path.unlink()
    except OSError:
        pass


def stop_port(port: int, name: str) -> None:
    pids = [pid for pid in pids_listening_on(port) if pid != os.getpid()]
    if not pids:
        log(f"{name} not listening on :{port}", prefix="stop")
        return
    for pid in pids:
        kill_pid(pid, f"{name} listener")


def start_hidden(
    *,
    name: str,
    cwd: Path,
    args: Sequence[str],
    pid_file: Path,
    stdout_log: Path,
    stderr_log: Path,
) -> int:
    ensure_dirs()
    stdout = stdout_log.open("ab")
    stderr = stderr_log.open("ab")
    creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    try:
        proc = subprocess.Popen(
            list(args),
            cwd=str(cwd),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    write_pid(pid_file, proc.pid)
    log(f"{name} process pid={proc.pid}", prefix="start")
    return proc.pid


def docker_compose(args: Sequence[str], *, prefix: str, warn_only: bool = True) -> bool:
    if not BOT_ROOT.exists():
        log(f"bot repo not found: {BOT_ROOT}", prefix=prefix)
        return False
    result = run(["docker", "compose", *args], cwd=BOT_ROOT, capture=True)
    if result.returncode == 0:
        return True
    detail = (result.stderr or result.stdout).strip()
    message = f"docker compose {' '.join(args)} failed"
    if detail:
        message += f": {detail}"
    if warn_only:
        log(message, prefix=prefix)
        return False
    raise RuntimeError(message)


def docker_container_status(name: str) -> str:
    result = run(
        ["docker", "ps", "-a", "--filter", f"name={name}", "--format", "{{.Status}}"],
        cwd=BOT_ROOT if BOT_ROOT.exists() else None,
        capture=True,
    )
    if result.returncode != 0:
        return "unknown (docker unavailable)"
    status = result.stdout.strip().splitlines()
    return status[0] if status else "not found"


def start(args: argparse.Namespace) -> int:
    ensure_dirs()
    if not args.no_grid:
        log("docker compose up -d grid ...", prefix="start")
        docker_compose(["up", "-d", "grid"], prefix="start", warn_only=True)

    if is_port_listening(BACKEND_PORT):
        log(f"backend already listening on :{BACKEND_PORT}", prefix="start")
    else:
        log(f"launching hidden backend uvicorn on :{BACKEND_PORT} ...", prefix="start")
        start_hidden(
            name="backend",
            cwd=BACKEND_DIR,
            args=[
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
                "--reload",
            ],
            pid_file=BACKEND_PID,
            stdout_log=LOG_DIR / "dashboard_backend.out.log",
            stderr_log=LOG_DIR / "dashboard_backend.err.log",
        )

    if is_port_listening(FRONTEND_PORT):
        log(f"frontend already listening on :{FRONTEND_PORT}", prefix="start")
    else:
        log(f"launching hidden frontend vite on :{FRONTEND_PORT} ...", prefix="start")
        if os.name == "nt":
            frontend_cmd = ["cmd.exe", "/d", "/c", "npm", "run", "dev"]
        else:
            frontend_cmd = ["npm", "run", "dev"]
        start_hidden(
            name="frontend",
            cwd=FRONTEND_DIR,
            args=frontend_cmd,
            pid_file=FRONTEND_PID,
            stdout_log=LOG_DIR / "dashboard_frontend.out.log",
            stderr_log=LOG_DIR / "dashboard_frontend.err.log",
        )

    backend_ok = wait_for_port(BACKEND_PORT, timeout_s=15)
    frontend_ok = wait_for_port(FRONTEND_PORT, timeout_s=15)
    if not backend_ok:
        log(
            f"backend did not start on :{BACKEND_PORT}; see logs/dashboard_backend.err.log",
            prefix="start",
        )
    if not frontend_ok:
        log(
            f"frontend did not start on :{FRONTEND_PORT}; see logs/dashboard_frontend.err.log",
            prefix="start",
        )
    log(f"done. Dashboard: http://127.0.0.1:{FRONTEND_PORT}  (backend API: :{BACKEND_PORT})", prefix="start")
    return 0 if backend_ok and frontend_ok else 1


def wait_for_port(port: int, *, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_port_listening(port):
            return True
        time.sleep(0.25)
    return False


def stop(args: argparse.Namespace) -> int:
    stop_pid_file(BACKEND_PID, "backend")
    stop_pid_file(FRONTEND_PID, "frontend")
    stop_port(BACKEND_PORT, "backend")
    stop_port(FRONTEND_PORT, "frontend")
    if not args.no_grid:
        log("docker compose stop grid ...", prefix="stop")
        docker_compose(["stop", "grid"], prefix="stop", warn_only=True)
    log("done. Live trading was not touched.", prefix="stop")
    return 0


def restart(args: argparse.Namespace) -> int:
    stop_args = argparse.Namespace(no_grid=args.no_grid)
    start_args = argparse.Namespace(no_grid=args.no_grid)
    stop(stop_args)
    time.sleep(2.0)
    return start(start_args)


def pid_file_status(path: Path, name: str) -> str:
    pid = read_pid(path)
    if pid is None:
        return f"{name} pid: none"
    return f"{name} pid: {pid} ({'running' if is_pid_running(pid) else 'stale'})"


def status(_: argparse.Namespace) -> int:
    backend_state = f"running (:{BACKEND_PORT})" if is_port_listening(BACKEND_PORT) else "stopped"
    frontend_state = f"running (:{FRONTEND_PORT})" if is_port_listening(FRONTEND_PORT) else "stopped"
    print(f"[status] dashboard backend: {backend_state}", flush=True)
    print(f"[status] dashboard frontend: {frontend_state}", flush=True)
    print(f"[status] {pid_file_status(BACKEND_PID, 'backend')}", flush=True)
    print(f"[status] {pid_file_status(FRONTEND_PID, 'frontend')}", flush=True)
    print(f"[status] grid container:     {docker_container_status('btc_pricer_15m_grid')}", flush=True)
    print(flush=True)
    print("[status] live switch:", flush=True)
    return live(argparse.Namespace(live_args=["status"]))


def profile_field(text: str, names: Iterable[str]) -> str:
    for name in names:
        match = re.search(rf"^\s*{re.escape(name)}\s*:\s*(.+?)\s*$", text, flags=re.I | re.M)
        if match:
            return match.group(1).strip()
    return ""


def read_profile(name: str = "infos") -> VpsProfile:
    profile_path = VPS_INFO_DIR / f"{name}.txt"
    text = profile_path.read_text(encoding="utf-8")
    ip_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
    if ip_match is None:
        raise RuntimeError(f"No IP found in VPS profile: {profile_path}")
    key_name = profile_field(text, ["use key", "ssh key"]) or "ssvi.pem"
    return VpsProfile(
        name=name,
        label=profile_field(text, ["label"]) or f"VPS {name}",
        host=ip_match.group(1),
        user=profile_field(text, ["user"]) or "ubuntu",
        directory=profile_field(text, ["dir"]) or "/opt/btc_pricer_15m_live",
        key=(VPS_INFO_DIR / key_name).resolve(),
    )


def profile_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DASHBOARD_VPS_INFO_DIR", str(VPS_INFO_DIR))
    try:
        profile = read_profile("infos")
    except OSError:
        return env
    env.setdefault("VPS_HOST", profile.host)
    env.setdefault("VPS_USER", profile.user)
    env.setdefault("VPS_DIR", profile.directory)
    env.setdefault("VPS_LABEL", profile.label)
    env.setdefault("SSH_KEY", str(profile.key))
    return env


def live(args: argparse.Namespace) -> int:
    bot_switch = BOT_ROOT / "scripts" / "live_switch.ps1"
    if not bot_switch.exists():
        raise RuntimeError(f"BTC live switch script not found: {bot_switch}")

    live_args = list(args.live_args or ["status"])
    command = live_args[0].lower() if live_args else "status"
    if command == "ireland":
        live_args = ["vps", "infos", *live_args[1:]]
    elif command == "vps" and len(live_args) == 1:
        live_args = ["vps", "infos"]
    elif command == "start":
        live_args = ["local", *live_args[1:]]

    ps = shutil.which("powershell.exe") or "powershell.exe"
    result = subprocess.run(
        [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(bot_switch), *live_args],
        cwd=str(BOT_ROOT),
        env=profile_env(),
        check=False,
    )
    return result.returncode


def tool_path(name: str, fallback: str | None = None) -> str:
    found = shutil.which(name)
    if found:
        return found
    if fallback and Path(fallback).exists():
        return fallback
    raise RuntimeError(f"{name} not found")


def quote_remote(value: str) -> str:
    if "'" in value:
        raise RuntimeError(f"remote shell quoting does not support single quotes: {value}")
    return f"'{value}'"


def ssh(profile: VpsProfile, remote_command: str, *, known_hosts: Path) -> None:
    ssh_exe = tool_path("ssh.exe" if os.name == "nt" else "ssh", r"C:\Windows\System32\OpenSSH\ssh.exe")
    result = run(
        [
            ssh_exe,
            "-i",
            profile.key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-o",
            "ConnectTimeout=12",
            f"{profile.user}@{profile.host}",
            remote_command,
        ],
        capture=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ssh command failed with exit code {result.returncode}")


def scp(profile: VpsProfile, source: Path | str, destination: str, *, known_hosts: Path) -> None:
    scp_exe = tool_path("scp.exe" if os.name == "nt" else "scp", r"C:\Windows\System32\OpenSSH\scp.exe")
    result = run(
        [
            scp_exe,
            "-i",
            profile.key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-o",
            "ConnectTimeout=12",
            source,
            destination,
        ],
        capture=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"scp failed with exit code {result.returncode}")


def should_ignore_copy(directory: str, names: list[str]) -> set[str]:
    path = Path(directory)
    ignored: set[str] = set()
    dir_names = {".git", "results", "__pycache__", ".pytest_cache", "backup"}
    file_names = {".env"}
    for name in names:
        child = path / name
        if name in dir_names or name in file_names:
            ignored.add(name)
        elif child.is_dir() and fnmatch.fnmatch(name, "backup_cleanup_*"):
            ignored.add(name)
        elif child.is_file() and (fnmatch.fnmatch(name, "*.pyc") or fnmatch.fnmatch(name, "*.log")):
            ignored.add(name)
    return ignored


def create_deploy_archive(stage_dir: Path, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w") as tar:
        for path in stage_dir.rglob("*"):
            tar.add(path, arcname=path.relative_to(stage_dir))


def setup_vps(args: argparse.Namespace) -> int:
    profile = read_profile(args.profile)
    bot_root = Path(args.bot_root).resolve() if args.bot_root else BOT_ROOT.resolve()
    env_path = bot_root / ".env"
    if not profile.key.exists():
        raise RuntimeError(f"SSH key not found: {profile.key}")
    if not env_path.exists():
        raise RuntimeError(f"Bot .env not found: {env_path}")

    ensure_dirs()
    known_hosts = TMP_DIR / "known_hosts_vps"
    archive = TMP_DIR / "btc_pricer_15m_deploy.tar"
    stage = TMP_DIR / "btc_pricer_15m_deploy_stage"
    remote_archive = "/tmp/btc_pricer_15m_deploy.tar"
    remote_dir_q = quote_remote(profile.directory)

    log(f"provisioning {profile.label}", prefix="setup-vps")
    ssh(
        profile,
        "\n".join(
            [
                "set -e",
                "export DEBIAN_FRONTEND=noninteractive",
                "sudo apt-get update",
                "sudo apt-get install -y ca-certificates curl git tar",
                "if ! command -v docker >/dev/null 2>&1; then",
                "  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh",
                "  sudo sh /tmp/get-docker.sh",
                "fi",
                f"sudo usermod -aG docker {profile.user} || true",
                f"sudo mkdir -p {remote_dir_q}/results {remote_dir_q}/results/calibration_inbox",
                f"sudo chown -R {profile.user}:{profile.user} {remote_dir_q}",
            ]
        ),
        known_hosts=known_hosts,
    )

    log("creating deploy archive", prefix="setup-vps")
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(bot_root, stage, ignore=should_ignore_copy)
    create_deploy_archive(stage, archive)

    log(f"copying code to {profile.label}", prefix="setup-vps")
    scp(profile, archive, f"{profile.user}@{profile.host}:{remote_archive}", known_hosts=known_hosts)
    ssh(
        profile,
        f"set -e; mkdir -p {remote_dir_q}; tar xf '{remote_archive}' -C {remote_dir_q}; "
        f"rm -f '{remote_archive}'; mkdir -p {remote_dir_q}/results {remote_dir_q}/results/calibration_inbox",
        known_hosts=known_hosts,
    )

    log("copying env without printing secrets", prefix="setup-vps")
    scp(profile, env_path, f"{profile.user}@{profile.host}:{profile.directory}/.env.tmp", known_hosts=known_hosts)
    ssh(profile, f"set -e; mv {remote_dir_q}/.env.tmp {remote_dir_q}/.env; chmod 600 {remote_dir_q}/.env", known_hosts=known_hosts)

    log("seeding live state files", prefix="setup-vps")
    results_dir = bot_root / "results"
    for name in ("15m_live_state.json", "15m_live_trades.csv", "15m_live_equity.csv"):
        path = results_dir / name
        if path.exists():
            scp(profile, path, f"{profile.user}@{profile.host}:{profile.directory}/results/{name}", known_hosts=known_hosts)
    ssh(
        profile,
        f"set -e; chmod 644 {remote_dir_q}/results/15m_live_state.json "
        f"{remote_dir_q}/results/15m_live_trades.csv {remote_dir_q}/results/15m_live_equity.csv 2>/dev/null || true",
        known_hosts=known_hosts,
    )

    if not args.skip_build:
        log("building VPS live image", prefix="setup-vps")
        ssh(profile, f"set -e; cd {remote_dir_q}; docker compose -f docker-compose.vps.yml build live", known_hosts=known_hosts)

    log(f"ready: run python manage.py live vps to move live trading to {profile.label}", prefix="setup-vps")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Polymarket dashboard and bot helpers.")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start grid plus hidden dashboard backend/frontend.")
    p_start.add_argument("--no-grid", action="store_true", help="Start only dashboard backend/frontend.")
    p_start.set_defaults(func=start)

    p_stop = sub.add_parser("stop", help="Stop dashboard backend/frontend and grid. Live trading is untouched.")
    p_stop.add_argument("--no-grid", action="store_true", help="Stop only dashboard backend/frontend.")
    p_stop.set_defaults(func=stop)

    p_restart = sub.add_parser("restart", help="Restart dashboard/grid.")
    p_restart.add_argument("--no-grid", action="store_true", help="Restart only dashboard backend/frontend.")
    p_restart.set_defaults(func=restart)

    p_status = sub.add_parser("status", help="Show dashboard, grid, and live-switch status.")
    p_status.set_defaults(func=status)

    p_live = sub.add_parser("live", help="Delegate live-trader switching/status to the BTC_pricer script.")
    p_live.add_argument("live_args", nargs=argparse.REMAINDER)
    p_live.set_defaults(func=live)

    p_setup = sub.add_parser("setup-vps", help="Provision/deploy the configured VPS.")
    p_setup.add_argument("--profile", default="infos")
    p_setup.add_argument("--bot-root", default="")
    p_setup.add_argument("--skip-build", action="store_true")
    p_setup.set_defaults(func=setup_vps)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args = parser.parse_args(["status"])
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[manage] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
