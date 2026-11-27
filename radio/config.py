"""Settings, paths and time helpers shared by every step."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
WORK_DIR = ROOT / "work"
EPISODES_DIR = ROOT / "episodes"
GUIDES_DIR = ROOT / "guides"
AUDIO_DIR = ROOT / "audio"


class RadioError(RuntimeError):
    """A failure that must stop the run before anything is published."""


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RadioError(f"{path} must contain a mapping")
    return data


def settings() -> dict:
    return load_yaml("settings.yaml")


def station() -> dict:
    return read_json(ROOT / "station.json")


def tz() -> ZoneInfo:
    return ZoneInfo(settings().get("timezone", "Asia/Tokyo"))


def now() -> dt.datetime:
    """Current time in the station's timezone. RADIO_NOW (ISO) overrides it for tests and reruns."""
    override = os.environ.get("RADIO_NOW")
    if override:
        t = dt.datetime.fromisoformat(override)
        return t if t.tzinfo else t.replace(tzinfo=tz())
    return dt.datetime.now(tz())


def today() -> str:
    return now().date().isoformat()


def read_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise RadioError(f"missing file: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=None if compact else 1)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)
