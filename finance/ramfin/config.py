"""Configuration loading. YAML for structure, environment for secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATHS = ("config/config.yaml", "config/config.example.yaml")


@dataclass
class BankAccount:
    key: str
    name: str
    institution: str
    kind: str  # chequing | loc | card | investment
    limit: float | None = None
    import_format: str | None = None


@dataclass
class Settings:
    raw: dict[str, Any]
    root: Path

    # ---- convenience accessors -------------------------------------------------
    @property
    def company(self) -> dict[str, Any]:
        return self.raw.get("company", {})

    @property
    def data_dir(self) -> Path:
        p = Path(self.raw.get("paths", {}).get("data_dir", "./data"))
        return p if p.is_absolute() else self.root / p

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ramfin.sqlite"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def sharepoint(self) -> dict[str, str]:
        return self.raw.get("sharepoint", {})

    @property
    def sources(self) -> dict[str, Any]:
        return self.raw.get("sources", {})

    @property
    def forecast(self) -> dict[str, Any]:
        return self.raw.get("forecast", {})

    @property
    def notify(self) -> dict[str, Any]:
        return self.raw.get("notify", {})

    @property
    def claude_model(self) -> str:
        return self.raw.get("claude", {}).get("model", "claude-opus-5")

    @property
    def claude_max_tokens(self) -> int:
        return int(self.raw.get("claude", {}).get("max_tokens", 16000))

    @property
    def bank_accounts(self) -> list[BankAccount]:
        out = []
        for a in self.raw.get("bank_accounts", []):
            out.append(BankAccount(
                key=a["key"], name=a["name"], institution=a.get("institution", ""),
                kind=a.get("kind", "chequing"), limit=a.get("limit"),
                import_format=a.get("import_format"),
            ))
        return out

    @property
    def labour_burden(self) -> float:
        return float(self.company.get("labour_burden_factor", 1.35))

    @property
    def gst_rate(self) -> float:
        return float(self.company.get("gst_rate", 0.05))

    def path(self, key: str) -> Path:
        p = Path(self.raw.get("paths", {}).get(key, ""))
        return p if p.is_absolute() else self.root / p

    def env(self, name: str, default: str | None = None) -> str | None:
        return os.environ.get(name, default)

    def payroll_anchor(self) -> date:
        v = self.forecast.get("payroll", {}).get("anchor_pay_date")
        if isinstance(v, date):
            return v
        return date.fromisoformat(str(v)) if v else date.today()


def load_settings(path: str | os.PathLike | None = None, root: str | os.PathLike | None = None) -> Settings:
    """Load settings from YAML. Falls back to the example config so tests and first runs work."""
    root_path = Path(root) if root else Path(__file__).resolve().parent.parent
    candidates = [Path(path)] if path else [root_path / p for p in DEFAULT_CONFIG_PATHS]
    for c in candidates:
        if c.exists():
            with open(c, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            return Settings(raw=raw, root=root_path)
    raise FileNotFoundError(f"No config found in {candidates}")


def settings_from_dict(raw: dict[str, Any], root: str | os.PathLike) -> Settings:
    return Settings(raw=raw, root=Path(root))
