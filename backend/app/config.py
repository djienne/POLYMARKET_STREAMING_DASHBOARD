import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: POLYMARKET_STREAMING_DASHBOARD/ (two up from this file).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class VpsProfile:
    name: str
    host: str
    user: str
    label: str
    ssh_key: Path
    dir: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    results_dir: Path = Field(default=Path("../BTC_pricer_15m/results"))
    config_dir: Path = Field(default=Path("../BTC_pricer_15m"))
    mode: Literal["dry_run", "live"] = "dry_run"
    default_instance_id: int = 100

    backend_host: str = "127.0.0.1"
    backend_port: int = 8799

    poll_interval_seconds: float = 2.0
    state_poll_interval_seconds: float = 5.0
    leaderboard_poll_interval_seconds: float = 30.0
    calibration_timeout_seconds: float = 360.0

    docker_container: str = "btc_pricer_15m_grid"
    # Short cadence so new "Model: UP=X% DOWN=Y%" lines surface within a second
    docker_poll_interval_seconds: float = 1.0

    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    # 1s cadence is still comfortably below Polymarket's documented /book limit.
    polymarket_poll_interval_seconds: float = 1.0
    polymarket_request_timeout_seconds: float = 6.0

    # VPS location probe — shows latency from the currently-active live trader
    # side. For location=vps, the probe SSHes out to measure trader→Polymarket
    # latency (not dashboard→Polymarket). IP/host is NOT hardcoded — set
    # VPS_HOST, VPS_USER, VPS_SSH_KEY in .env (gitignored). If VPS_HOST is
    # empty the probe silently falls back to local-only measurement.
    vps_host: str = ""
    vps_user: str = "ubuntu"
    vps_label: str = "VPS"
    vps_ssh_key: Path = Field(default=Path("vps_infos/vps.pem"))
    vps_dir: str = "/opt/btc_pricer_15m_live"
    polymarket_probe_interval_seconds: float = 30.0

    log_level: str = "INFO"

    @staticmethod
    def _resolve(p: Path) -> Path:
        p = p.expanduser()
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        else:
            p = p.resolve()
        return p

    @property
    def resolved_results_dir(self) -> Path:
        return self._resolve(self.results_dir)

    @property
    def resolved_config_dir(self) -> Path:
        return self._resolve(self.config_dir)

    def state_snapshot_path(self) -> Path:
        return self.resolved_results_dir / "state_snapshot.json"

    def live_state_path(self) -> Path:
        return self.resolved_results_dir / "15m_live_state.json"

    def trades_path(self) -> Path:
        name = "trades.csv" if self.mode == "dry_run" else "15m_live_trades.csv"
        return self.resolved_results_dir / name

    def terminal_path(self) -> Path:
        return self.resolved_results_dir / "terminal_data.json"

    def leaderboard_path(self) -> Path:
        return self.resolved_results_dir / "leaderboard.csv"

    def lock_path(self) -> Path:
        return self.resolved_results_dir / "trader.lock"

    def orderbook_path(self) -> Path:
        return self.resolved_results_dir / "15m_orderbook.csv"

    def trader_log_paths(self) -> list[Path]:
        return [
            self.resolved_results_dir / "trader.log",
            self.resolved_results_dir / "15m_trading.log",
        ]

    def grid_config_path(self) -> Path:
        return self.resolved_config_dir / "config_grid.json"

    def live_config_path(self) -> Path:
        return self.resolved_config_dir / "config_trader_live.json"

    def live_location_path(self) -> Path:
        """Marker file written by live_manager.py — "local" | "vps" | "stopped"."""
        return self.resolved_results_dir / ".live_location"

    def resolved_vps_ssh_key(self) -> Path:
        return self._resolve(self.vps_ssh_key)

    @staticmethod
    def _friendly_vps_label(name: str) -> str:
        words = [chunk for chunk in re.split(r"[_\-\s]+", name.strip()) if chunk]
        if not words:
            return "VPS"
        return "VPS " + " ".join(w.capitalize() for w in words)

    def _parse_vps_profile_file(self, name: str, path: Path) -> Optional[VpsProfile]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        host_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
        key_match = re.search(r"use key:\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        label_match = re.search(r"label:\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        user_match = re.search(r"user:\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        dir_match = re.search(r"dir:\s*([^\r\n]+)", text, flags=re.IGNORECASE)
        if host_match is None:
            return None
        ssh_key = (
            self._resolve(Path("vps_infos") / key_match.group(1).strip())
            if key_match is not None
            else self.resolved_vps_ssh_key()
        )
        home_ssh_key = Path.home() / ".ssh" / ssh_key.name
        if home_ssh_key.exists():
            ssh_key = home_ssh_key.resolve()
        label = (
            label_match.group(1).strip()
            if label_match is not None
            else self._friendly_vps_label(name)
        )
        user = user_match.group(1).strip() if user_match is not None else self.vps_user
        vps_dir = dir_match.group(1).strip() if dir_match is not None else self.vps_dir
        return VpsProfile(
            name=name,
            host=host_match.group(1),
            user=user,
            label=label,
            ssh_key=ssh_key,
            dir=vps_dir,
        )

    def vps_profile(self, profile_name: Optional[str] = None) -> Optional[VpsProfile]:
        """Resolve a named VPS profile from vps_infos/*.txt or the default env config.

        - None / "" / "default" / "vps" => use .env-backed default VPS
        - any other name => load vps_infos/<name>.txt
        """
        normalized = (profile_name or "").strip()
        if normalized in {"", "default", "vps"}:
            if not self.vps_host:
                return None
            ssh_key = self.resolved_vps_ssh_key()
            home_ssh_key = Path.home() / ".ssh" / ssh_key.name
            if home_ssh_key.exists():
                ssh_key = home_ssh_key.resolve()
            return VpsProfile(
                name="default",
                host=self.vps_host,
                user=self.vps_user,
                label=self.vps_label,
                ssh_key=ssh_key,
                dir=self.vps_dir,
            )
        path = self._resolve(Path("vps_infos") / f"{normalized}.txt")
        if not path.exists():
            return None
        return self._parse_vps_profile_file(normalized, path)


settings = Settings()
