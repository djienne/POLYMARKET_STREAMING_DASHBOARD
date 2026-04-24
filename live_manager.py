"""Python live-trader orchestration for BTC_pricer_15m.

Replaces scripts/live_switch.{ps1,sh} and scripts/vps_state_sync.{ps1,sh}.
Invoked by manage.py's ``live`` subcommand (via :func:`dispatch`) and by a
detached subprocess when the sync loop is running
(``python live_manager.py --sync-loop <profile>``).
"""
from __future__ import annotations

import os
import base64
import json
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

from manage import (
    BOT_ROOT,
    CommandResult,
    VPS_INFO_DIR,
    VpsProfile,
    is_pid_running,
    kill_pid,
    log,
    read_pid,
    read_profile,
    tool_path,
)


# All subprocess invocations in this module pass CREATE_NO_WINDOW on Windows.
# The detached sync-loop child has no console (DETACHED_PROCESS), so without
# this flag each ssh.exe/scp.exe it spawns would create a fresh visible
# console window — that flooded the desktop until the user killed the loop.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(
    args,
    *,
    capture: bool = True,
    cwd=None,
    env=None,
) -> CommandResult:
    text_args = [str(a) for a in args]
    kwargs: dict = dict(
        text=True,
        capture_output=capture,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    if os.name == "nt":
        kwargs["creationflags"] = _NO_WINDOW
    completed = subprocess.run(text_args, **kwargs)
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = BOT_ROOT / "results"
LOCATION_PATH = RESULTS_DIR / ".live_location"
SYNC_PID_PATH = RESULTS_DIR / ".vps_sync.pid"
SYNC_HEARTBEAT_PATH = RESULTS_DIR / ".vps_sync_last"
SYNC_LOG_PATH = RESULTS_DIR / ".vps_sync.log"
SYNC_ERR_PATH = RESULTS_DIR / ".vps_sync.err"
LIVE_HISTORY_BACKUP_DIR = RESULTS_DIR / "live_history_backups"

SYNC_INTERVAL_S = 1
LIVE_HISTORY_BACKUP_INTERVAL_S = 300
LIVE_HISTORY_BACKUP_KEEP = 288
SSH_TIMEOUT_S = 10
SYNC_SSH_TIMEOUT_S = 8

LIVE_CONTAINER = "btc_pricer_15m_live"
OFFLOAD_CONTAINER = "btc_pricer_15m_offload"
OFFLOAD_COMPOSE = BOT_ROOT / "docker-compose.offload.yml"
VPS_COMPOSE = "docker-compose.vps.yml"

REQUIRED_STATE_FILES = (
    "15m_live_state.json",
)
OPTIONAL_STATE_FILES = (
    "15m_live_trades.csv",
    "15m_live_equity.csv",
    "terminal_data.json",
    ".clob_latency_ms",
    "single_trader.lock",
)
LIVE_HISTORY_FILES = (
    "15m_live_state.json",
    "15m_live_trades.csv",
    "15m_live_equity.csv",
)
PUSH_STATE_FILES = (
    "15m_live_state.json",
    "15m_live_trades.csv",
    "15m_live_equity.csv",
    "terminal_data.json",
    ".clob_latency_ms",
)

_LAST_HISTORY_BACKUP_AT = 0.0


# ---------------------------------------------------------------------------
# SSH / SCP helpers (match live_switch semantics: StrictHostKeyChecking=no)
# ---------------------------------------------------------------------------

# Resolved once at import. Calling shutil.which on every pull cycle was a
# subtle race risk: a transient PATH stat hiccup (antivirus scanning, file
# system pressure) could make tool_path raise or return a stale path that
# CreateProcess then rejects with WinError 2.
_SSH_EXE: Optional[str] = None
_SCP_EXE: Optional[str] = None


def _ssh_exe() -> str:
    global _SSH_EXE
    if _SSH_EXE is None:
        _SSH_EXE = tool_path(
            "ssh.exe" if os.name == "nt" else "ssh",
            r"C:\Windows\System32\OpenSSH\ssh.exe",
        )
    return _SSH_EXE


def _scp_exe() -> str:
    global _SCP_EXE
    if _SCP_EXE is None:
        _SCP_EXE = tool_path(
            "scp.exe" if os.name == "nt" else "scp",
            r"C:\Windows\System32\OpenSSH\scp.exe",
        )
    return _SCP_EXE


def _ssh_args(profile: VpsProfile, *, timeout: int = SSH_TIMEOUT_S) -> list[str]:
    return [
        _ssh_exe(),
        "-i", str(profile.key),
        "-o", "StrictHostKeyChecking=no",
        "-o", f"ConnectTimeout={timeout}",
        f"{profile.user}@{profile.host}",
    ]


def _scp_args(profile: VpsProfile, *, timeout: int = SSH_TIMEOUT_S) -> list[str]:
    return [
        _scp_exe(),
        "-i", str(profile.key),
        "-o", "StrictHostKeyChecking=no",
        "-o", f"ConnectTimeout={timeout}",
    ]


def ssh_run(
    profile: VpsProfile,
    remote_command: str,
    *,
    capture: bool = False,
    timeout: int = SSH_TIMEOUT_S,
):
    return _run(
        _ssh_args(profile, timeout=timeout) + [remote_command],
        capture=capture,
    )


def _quote_remote(value: str) -> str:
    if "'" in value:
        raise RuntimeError(f"remote shell quoting does not support single quotes in: {value}")
    return f"'{value}'"


# ---------------------------------------------------------------------------
# Location marker (.live_location)
# ---------------------------------------------------------------------------

def _read_location_raw() -> str:
    try:
        return LOCATION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "stopped"


def get_location() -> str:
    raw = _read_location_raw()
    if raw in ("local", "stopped", "vps"):
        return raw
    if raw.startswith("vps:"):
        return "vps"
    return "stopped"


def get_profile_name() -> Optional[str]:
    raw = _read_location_raw()
    if raw.startswith("vps:"):
        return raw[4:]
    return None


def set_location(kind: str, profile: Optional[str] = None) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if kind == "vps" and profile and profile != "default":
        LOCATION_PATH.write_text(f"vps:{profile}", encoding="ascii")
    else:
        LOCATION_PATH.write_text(kind, encoding="ascii")


# ---------------------------------------------------------------------------
# Profile discovery
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    if not VPS_INFO_DIR.exists():
        return []
    return sorted({p.stem for p in VPS_INFO_DIR.glob("*.txt")})


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _docker_ps_names(filter_name: str) -> list[str]:
    result = _run(
        ["docker", "ps", "--filter", f"name={filter_name}", "--format", "{{.Names}}"],
        capture=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def local_live_running() -> bool:
    return LIVE_CONTAINER in _docker_ps_names(LIVE_CONTAINER)


def local_offload_running() -> bool:
    return OFFLOAD_CONTAINER in _docker_ps_names(OFFLOAD_CONTAINER)


def _docker_compose(args: list[str]) -> None:
    result = _run(["docker", "compose", *args], cwd=BOT_ROOT, capture=False)
    if result.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(args)} failed with exit code {result.returncode}")


def start_local_live() -> None:
    _docker_compose(["--profile", "local-live", "up", "-d", "live"])


def stop_local_live() -> None:
    if local_live_running():
        _docker_compose(["--profile", "local-live", "stop", "live"])


def stop_local_offload() -> None:
    try:
        if local_offload_running():
            result = _run(["docker", "stop", OFFLOAD_CONTAINER], capture=True)
            if result.returncode == 0:
                log("stopped local calibration offload container", prefix="live")
            else:
                log(f"docker stop {OFFLOAD_CONTAINER} failed (exit {result.returncode})", prefix="live")
    except Exception as exc:
        log(f"local offload status unavailable: {exc}", prefix="live")


def start_local_offload(profile: VpsProfile) -> None:
    log(
        "local calibration offload disabled; VPS live will use its own calculations only",
        prefix="live",
    )
    stop_local_offload()


# ---------------------------------------------------------------------------
# VPS status (remote docker ps over SSH)
# ---------------------------------------------------------------------------

def vps_live_running(profile: VpsProfile) -> bool:
    result = ssh_run(
        profile,
        f"docker ps --filter name={LIVE_CONTAINER} --format '{{{{.Names}}}}'",
        capture=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ssh failed while checking VPS live on {profile.label} ({profile.host}): exit {result.returncode}"
        )
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return LIVE_CONTAINER in names


def count_running_vps_live() -> int:
    count = 0
    for name in list_profiles():
        try:
            if vps_live_running(read_profile(name)):
                count += 1
        except Exception as exc:
            raise RuntimeError(f"could not check VPS live status for {name}: {exc}") from exc
    return count


def stop_all_vps_live() -> list[str]:
    stopped: list[str] = []
    for name in list_profiles():
        profile = read_profile(name)
        try:
            running = vps_live_running(profile)
        except Exception as exc:
            raise RuntimeError(
                f"could not check VPS live status for {profile.label} ({profile.host}): {exc}"
            ) from exc
        if running:
            log(f"stopping VPS live on {profile.label}", prefix="live")
            dir_q = _quote_remote(profile.directory)
            result = ssh_run(
                profile,
                f"cd {dir_q} && docker compose -f {VPS_COMPOSE} stop live",
                capture=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"remote stop failed on {profile.label} (exit {result.returncode})")
            if vps_live_running(profile):
                raise RuntimeError(f"VPS live is still running on {profile.label} after stop")
            stopped.append(name)
    if not stopped:
        log("no VPS live container running on any configured target", prefix="live")
    return stopped


def check_mutual_exclusion() -> None:
    local_up = local_live_running()
    vps_count = count_running_vps_live()
    if local_up and vps_count > 0:
        raise RuntimeError(
            "live is running in TWO places (local + one or more VPS targets). "
            "Run `python manage.py live stop` first."
        )
    if vps_count > 1:
        raise RuntimeError(
            "live is running on MULTIPLE VPS targets. Run `python manage.py live stop` first."
        )


# ---------------------------------------------------------------------------
# State transfer (push up / pull down)
# ---------------------------------------------------------------------------

def ensure_remote_results_writable(profile: VpsProfile) -> None:
    dir_q = _quote_remote(profile.directory)
    # Old files may be owned by root from a prior run that started live as root;
    # chown them so the non-root user can overwrite via scp without deleting
    # historical state first.
    remote = (
        f"sudo mkdir -p {dir_q}/results {dir_q}/results/calibration_inbox && "
        f"sudo chown -R {profile.user}:{profile.user} {dir_q}/results"
    )
    result = ssh_run(profile, remote, capture=False)
    if result.returncode != 0:
        raise RuntimeError(f"ensure_remote_results_writable failed (exit {result.returncode})")


def _safe_reason(reason: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in reason)[:40]


def _prune_live_history_backups() -> None:
    try:
        backups = sorted(
            [p for p in LIVE_HISTORY_BACKUP_DIR.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return
    for old in backups[LIVE_HISTORY_BACKUP_KEEP:]:
        try:
            shutil.rmtree(old)
        except OSError:
            pass


def backup_live_history(reason: str) -> Optional[Path]:
    existing = [RESULTS_DIR / name for name in LIVE_HISTORY_FILES if (RESULTS_DIR / name).exists()]
    if not existing:
        return None

    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    dest = LIVE_HISTORY_BACKUP_DIR / f"{stamp}_{_safe_reason(reason)}"
    try:
        dest.mkdir(parents=True, exist_ok=False)
        for path in existing:
            shutil.copy2(path, dest / path.name)
        _prune_live_history_backups()
    except OSError as exc:
        log(f"live history backup failed ({reason}): {exc}", prefix="live")
        return None
    return dest


def maybe_backup_live_history(reason: str) -> None:
    global _LAST_HISTORY_BACKUP_AT
    now = time.monotonic()
    if now - _LAST_HISTORY_BACKUP_AT < LIVE_HISTORY_BACKUP_INTERVAL_S:
        return
    if backup_live_history(reason):
        _LAST_HISTORY_BACKUP_AT = now


def backup_remote_live_history(profile: VpsProfile, reason: str) -> None:
    dir_q = _quote_remote(profile.directory)
    reason_q = _quote_remote(_safe_reason(reason))
    remote = (
        "set -e; "
        "stamp=$(date -u +%Y%m%d_%H%M%S); "
        f"backup_dir={dir_q}/results/live_history_backups/${{stamp}}_{reason_q}; "
        "mkdir -p \"$backup_dir\"; "
        f"for name in {' '.join(LIVE_HISTORY_FILES)}; do "
        f"  if test -f {dir_q}/results/$name; then cp -p {dir_q}/results/$name \"$backup_dir/$name\"; fi; "
        "done; "
        f"find {dir_q}/results/live_history_backups -mindepth 1 -maxdepth 1 -type d | sort -r | "
        f"tail -n +{LIVE_HISTORY_BACKUP_KEEP + 1} | xargs -r rm -rf"
    )
    result = ssh_run(profile, remote, capture=False)
    if result.returncode != 0:
        raise RuntimeError(f"remote live history backup failed (exit {result.returncode})")


def push_state_to_vps(profile: VpsProfile) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _guard_against_history_regression(profile, source="local", target="VPS")
    backup_live_history("pre_push_local")
    backup_remote_live_history(profile, "pre_push_remote")
    ensure_remote_results_writable(profile)
    pushed: list[str] = []
    for name in PUSH_STATE_FILES:
        local_path = RESULTS_DIR / name
        if local_path.exists():
            dest = f"{profile.user}@{profile.host}:{profile.directory}/results/{name}"
            result = _run(_scp_args(profile) + [str(local_path), dest], capture=False)
            if result.returncode != 0:
                raise RuntimeError(f"failed to push {name} to {profile.label}")
            pushed.append(name)
    if pushed:
        log(f"pushed to VPS: {' '.join(pushed)}", prefix="live")
    else:
        log("no live state files to push", prefix="live")


def _ssh_cat(profile: VpsProfile, remote_path: str) -> tuple[int, bytes]:
    """One round-trip pull: streams remote file content over ssh stdout.

    Replaces the older ``test -f`` + ``scp tmpfile`` two-call pattern.
    The previous design wrote a ``__sync_tmp__*`` file in results/ then
    ``os.replace``-d it onto the final name; on Windows, real-time AV
    scanning of the brand-new temp file would briefly remove it from
    disk in the microseconds between scp finishing and the rename,
    making os.replace fail with WinError 2. Skipping the temp file
    eliminates the race entirely.

    Exit codes (from the composite remote command):
      0  → file present, stdout = its raw bytes
      44 → file absent
      *  → ssh/network error
    """
    remote_cmd = (
        f"if test -f '{remote_path}'; then cat '{remote_path}'; else exit 44; fi"
    )
    text_args = _ssh_args(profile, timeout=SYNC_SSH_TIMEOUT_S) + [remote_cmd]
    kwargs: dict = dict(capture_output=True)
    if os.name == "nt":
        kwargs["creationflags"] = _NO_WINDOW
    completed = subprocess.run([str(a) for a in text_args], **kwargs)
    return completed.returncode, completed.stdout or b""


def _closed_position_count_from_bytes(content: bytes) -> Optional[int]:
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    closed = data.get("closed_positions")
    return len(closed) if isinstance(closed, list) else None


def _closed_position_count_from_file(path: Path) -> Optional[int]:
    try:
        return _closed_position_count_from_bytes(path.read_bytes())
    except OSError:
        return None


def _remote_closed_position_count(profile: VpsProfile) -> Optional[int]:
    rc, content = _ssh_cat(profile, f"{profile.directory}/results/15m_live_state.json")
    if rc != 0:
        return None
    return _closed_position_count_from_bytes(content)


def _guard_against_history_regression(
    profile: VpsProfile,
    *,
    source: str,
    target: str,
    remote_count: Optional[int] = None,
) -> None:
    local_count = _closed_position_count_from_file(RESULTS_DIR / "15m_live_state.json")
    if remote_count is None:
        remote_count = _remote_closed_position_count(profile)
    if local_count is None or remote_count is None:
        return

    if source == "local":
        source_count, target_count = local_count, remote_count
    else:
        source_count, target_count = remote_count, local_count

    if source_count < target_count:
        raise RuntimeError(
            f"refusing to replace {target} live history with older {source} state "
            f"({source_count} closed positions < {target_count})"
        )


def _write_pulled_file(profile: VpsProfile, name: str, content: bytes) -> bool:
    local_path = RESULTS_DIR / name

    if name == "15m_live_state.json":
        remote_count = _closed_position_count_from_bytes(content)
        try:
            _guard_against_history_regression(
                profile,
                source="VPS",
                target="local",
                remote_count=remote_count,
            )
        except RuntimeError as exc:
            log(str(exc), prefix="live")
            return True

    if name in LIVE_HISTORY_FILES and local_path.exists():
        try:
            if local_path.read_bytes() != content:
                maybe_backup_live_history("pre_pull_overwrite")
        except OSError:
            maybe_backup_live_history("pre_pull_overwrite")

    try:
        local_path.write_bytes(content)
    except OSError:
        return False
    return True


def _pull_one_file(profile: VpsProfile, name: str, *, required: bool) -> bool:
    remote_path = f"{profile.directory}/results/{name}"
    rc, content = _ssh_cat(profile, remote_path)

    if rc == 44:
        if required:
            log(f"required remote state file missing; preserving local {name}", prefix="live")
        return not required

    if rc != 0:
        return False

    return _write_pulled_file(profile, name, content)


def _pull_files_batched(profile: VpsProfile, names: tuple[str, ...]) -> Optional[dict[str, bytes | None]]:
    names_json = json.dumps(list(names), separators=(",", ":"))
    remote = "\n".join(
        [
            "python3 - <<'PY'",
            "import base64, json, pathlib",
            f"root = pathlib.Path({profile.directory!r}) / 'results'",
            f"names = json.loads({names_json!r})",
            "out = {}",
            "for name in names:",
            "    path = root / name",
            "    try:",
            "        out[name] = {'ok': True, 'data': base64.b64encode(path.read_bytes()).decode('ascii')}",
            "    except FileNotFoundError:",
            "        out[name] = {'ok': False, 'missing': True}",
            "    except OSError as exc:",
            "        out[name] = {'ok': False, 'error': str(exc)}",
            "print(json.dumps(out, separators=(',', ':')))",
            "PY",
        ]
    )
    result = ssh_run(profile, remote, capture=True, timeout=SYNC_SSH_TIMEOUT_S)
    if result.returncode != 0:
        return None
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    pulled: dict[str, bytes | None] = {}
    for name in names:
        entry = raw.get(name)
        if not isinstance(entry, dict) or not entry.get("ok"):
            pulled[name] = None
            continue
        try:
            pulled[name] = base64.b64decode(str(entry.get("data") or ""), validate=True)
        except (ValueError, TypeError):
            return None
    return pulled


def _pull_all_files_once(profile: VpsProfile) -> bool:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    names = (*REQUIRED_STATE_FILES, *OPTIONAL_STATE_FILES)
    pulled = _pull_files_batched(profile, names)
    if pulled is not None:
        ok = True
        required = set(REQUIRED_STATE_FILES)
        for name in names:
            content = pulled.get(name)
            if content is None:
                if name in required:
                    log(f"required remote state file missing; preserving local {name}", prefix="live")
                    ok = False
                continue
            if not _write_pulled_file(profile, name, content):
                ok = False
        return ok

    # Fallback for hosts without python3/base64 support or transient parse
    # failures. This is slower because it opens one SSH session per file.
    ok = True
    for name in REQUIRED_STATE_FILES:
        if not _pull_one_file(profile, name, required=True):
            ok = False
    for name in OPTIONAL_STATE_FILES:
        if not _pull_one_file(profile, name, required=False):
            ok = False
    return ok


def pull_state_from_vps_once(profile: VpsProfile) -> None:
    log(f"pulling final VPS state from {profile.label} ({profile.host})", prefix="live")
    if not _pull_all_files_once(profile):
        raise RuntimeError(f"failed to pull final VPS state from {profile.label}")


# ---------------------------------------------------------------------------
# Sync loop (parent spawn + child body)
# ---------------------------------------------------------------------------

def run_sync_loop_body(profile: VpsProfile) -> None:
    print(
        f"[vps_state_sync] started pid={os.getpid()} cadence={SYNC_INTERVAL_S}s "
        f"profile={profile.name}",
        flush=True,
    )
    while True:
        # Loop survival is the core requirement — any exception inside one pull
        # cycle must not kill the whole loop. Log it and keep going.
        try:
            ok = _pull_all_files_once(profile)
        except Exception as exc:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            print(f"[vps_state_sync {ts}] pull raised: {exc!r}", flush=True)
            print(traceback.format_exc(), flush=True)
            ok = False
        if ok:
            try:
                SYNC_HEARTBEAT_PATH.write_text(str(int(time.time())), encoding="ascii")
            except OSError as exc:
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                print(f"[vps_state_sync {ts}] heartbeat write failed: {exc!r}", flush=True)
        else:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            print(f"[vps_state_sync {ts}] pull failed", flush=True)
        time.sleep(SYNC_INTERVAL_S)


def start_sync_loop(profile: VpsProfile) -> int:
    stop_sync_loop()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--sync-loop",
        profile.name,
    ]
    env = os.environ.copy()
    env["DASHBOARD_VPS_INFO_DIR"] = str(VPS_INFO_DIR)

    log_f = open(SYNC_LOG_PATH, "ab", buffering=0)
    err_f = open(SYNC_ERR_PATH, "ab", buffering=0)
    try:
        popen_kwargs: dict = dict(
            args=args,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=err_f,
            close_fds=True,
        )
        if os.name == "nt":
            # CREATE_BREAKAWAY_FROM_JOB escapes the parent's Windows Job Object
            # (Git Bash, Claude, some IDE terminals wrap commands in a job that
            # kills descendants on parent exit — even DETACHED_PROCESS children).
            # If the parent job forbids breakaway, fall back without it.
            base_flags = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            popen_kwargs["creationflags"] = base_flags | 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
            try:
                proc = subprocess.Popen(**popen_kwargs)
            except OSError:
                popen_kwargs["creationflags"] = base_flags
                proc = subprocess.Popen(**popen_kwargs)
        else:
            popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(**popen_kwargs)
    finally:
        log_f.close()
        err_f.close()

    SYNC_PID_PATH.write_text(str(proc.pid), encoding="ascii")
    log(f"started vps_state_sync loop (pid={proc.pid}, profile={profile.name})", prefix="live")
    return proc.pid


def stop_sync_loop() -> None:
    pid = read_pid(SYNC_PID_PATH)
    if pid is not None and is_pid_running(pid):
        kill_pid(pid, "vps_state_sync")
    try:
        SYNC_PID_PATH.unlink()
    except OSError:
        pass


def sync_loop_alive() -> bool:
    pid = read_pid(SYNC_PID_PATH)
    return pid is not None and is_pid_running(pid)


# ---------------------------------------------------------------------------
# Auto-heal
# ---------------------------------------------------------------------------

def auto_heal_sync_loop() -> bool:
    if get_location() != "vps":
        return False
    if sync_loop_alive():
        return False
    name = get_profile_name()
    if not name:
        return False
    try:
        profile = read_profile(name)
    except (OSError, RuntimeError) as exc:
        log(f"cannot auto-heal: profile '{name}' unreadable: {exc}", prefix="live")
        return False
    try:
        running = vps_live_running(profile)
    except Exception as exc:
        log(f"cannot auto-heal: VPS unreachable ({exc})", prefix="live")
        return False
    if not running:
        log(
            f"cannot auto-heal: VPS live container not running on {profile.label}",
            prefix="live",
        )
        return False
    new_pid = start_sync_loop(profile)
    log(f"auto-healed vps_state_sync loop (pid={new_pid})", prefix="live")
    return True


# ---------------------------------------------------------------------------
# Top-level switch actions
# ---------------------------------------------------------------------------

def switch_stop() -> None:
    log("stopping both sides (idempotent)", prefix="live")
    try:
        if local_live_running():
            _docker_compose(["--profile", "local-live", "stop", "live"])
    except Exception as exc:
        log(f"local live status unavailable: {exc}", prefix="live")
    try:
        stop_all_vps_live()
    except Exception as exc:
        log(f"VPS stop skipped: {exc}", prefix="live")
    stop_sync_loop()
    stop_local_offload()
    set_location("stopped")
    log("live is now STOPPED", prefix="live")


def switch_local() -> None:
    log("switching to LOCAL", prefix="live")
    location_name = get_profile_name()
    prior_kind = get_location()
    stopped_profiles = stop_all_vps_live()

    target_name = location_name
    if not target_name and len(stopped_profiles) == 1:
        target_name = stopped_profiles[0]

    stop_sync_loop()
    stop_local_offload()

    if prior_kind == "vps" or stopped_profiles:
        if target_name:
            pull_state_from_vps_once(read_profile(target_name))
        else:
            log("no single VPS target identified; skipping final pull", prefix="live")
    else:
        log("location is not VPS; skipping final VPS pull", prefix="live")

    check_mutual_exclusion()
    if count_running_vps_live() > 0:
        raise RuntimeError("A VPS live container is still running; aborting to avoid dual trading")

    start_local_live()
    set_location("local")
    log("LIVE is now LOCAL", prefix="live")


def switch_vps(profile_name: str) -> None:
    name = profile_name or "infos"
    profile = read_profile(name)
    log(f"switching to VPS ({profile.label})", prefix="live")

    if local_live_running():
        _docker_compose(["--profile", "local-live", "stop", "live"])
        log("stopped local live container", prefix="live")
    stop_all_vps_live()

    push_state_to_vps(profile)
    dir_q = _quote_remote(profile.directory)
    result = ssh_run(
        profile,
        f"cd {dir_q} && docker compose -f {VPS_COMPOSE} up -d live",
        capture=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"remote `docker compose up -d live` failed (exit {result.returncode})")

    check_mutual_exclusion()
    if not vps_live_running(profile):
        raise RuntimeError(f"VPS live did not start on {profile.label}")

    start_sync_loop(profile)
    start_local_offload(profile)
    set_location("vps", name)
    log(f"LIVE is now on {profile.label}", prefix="live")


def show_status() -> None:
    raw = _read_location_raw()
    kind = get_location()
    print(f"location: {raw}", flush=True)

    if kind == "vps":
        name = get_profile_name() or "infos"
        try:
            active = read_profile(name)
            print(f"active label:     {active.label}", flush=True)
            print(f"active host:      {active.host}", flush=True)
        except Exception as exc:
            print(f"active profile unreadable: {exc}", flush=True)

    try:
        local_up = "yes" if local_live_running() else "no"
    except Exception:
        local_up = "unknown"
    print(f"local container:  {local_up}", flush=True)

    for name in list_profiles():
        try:
            prof = read_profile(name)
        except Exception as exc:
            print(f"vps {name}: unreadable ({exc})", flush=True)
            continue
        try:
            running = "yes" if vps_live_running(prof) else "no"
        except Exception:
            running = "unknown"
        label = f"vps {name}:"
        print(f"{label:<17} {running} ({prof.label})", flush=True)

    pid = read_pid(SYNC_PID_PATH)
    if pid is not None:
        if is_pid_running(pid):
            print(f"vps sync loop:    running (pid={pid})", flush=True)
        else:
            print("vps sync loop:    stopped (stale pid file)", flush=True)
    else:
        print("vps sync loop:    stopped", flush=True)

    try:
        last = int(SYNC_HEARTBEAT_PATH.read_text(encoding="utf-8").strip())
        age = max(0, int(time.time()) - last)
        print(f"last sync:        {age}s ago", flush=True)
    except (OSError, ValueError):
        pass

    try:
        offload = "running (docker)" if local_offload_running() else "stopped"
    except Exception:
        offload = "unknown"
    print(f"local offload:    {offload}", flush=True)

    # Auto-heal after printing — runs silently when nothing to do, announces when it acts.
    auto_heal_sync_loop()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(live_args: list[str]) -> int:
    if not live_args:
        live_args = ["status"]
    cmd = live_args[0].lower()
    try:
        if cmd == "status":
            show_status()
            return 0
        if cmd == "stop":
            switch_stop()
            return 0
        if cmd == "local":
            switch_local()
            return 0
        if cmd == "vps":
            name = live_args[1] if len(live_args) > 1 else "infos"
            switch_vps(name)
            return 0
        if cmd == "heal":
            changed = auto_heal_sync_loop()
            log("heal applied" if changed else "no heal needed", prefix="live")
            return 0
        if (VPS_INFO_DIR / f"{cmd}.txt").exists():
            switch_vps(cmd)
            return 0
        log(
            f"unknown live command: {cmd}. "
            "Use: status | stop | local | vps [profile] | heal | <profile-name>",
            prefix="live",
        )
        return 2
    except Exception as exc:
        log(f"ERROR: {exc}", prefix="live")
        return 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "--sync-loop":
        run_sync_loop_body(read_profile(argv[1]))
    else:
        sys.exit(dispatch(argv))
