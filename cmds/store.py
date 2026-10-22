"""Load and save the YAML command store."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class StoreError(Exception):
    """A problem reading or writing the store file (exit code 2)."""


@dataclass
class Entry:
    tech: str
    command: str
    description: str = ""

    @property
    def top(self) -> str:
        return self.tech.partition("/")[0]


HEADER = "# cmds notebook. One entry per list item; tech may be nested like azure/pim.\n"



def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "cmds"


def store_path() -> Path:
    """$CMDS_FILE, else the path saved with `cmds file`, else ~/.config/cmds/commands.yaml."""
    if override := os.environ.get("CMDS_FILE"):
        return Path(override).expanduser()
    if configured := load_settings().get("file"):
        return Path(configured).expanduser()
    return config_dir() / "commands.yaml"


def load(path: Path) -> list[Entry]:
    """Read entries in file order. Creates an empty file on first run."""
    if not path.exists():
        save(path, [])
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as exc:
        raise StoreError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, list):
        raise StoreError(f"{path}: expected a YAML list of entries")
    entries = []
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict) or not item.get("tech") or not item.get("command"):
            raise StoreError(f"{path}: entry {i} needs 'tech' and 'command'")
        entries.append(Entry(str(item["tech"]).strip("/"), str(item["command"]), str(item.get("description") or "")))
    return entries


def _dump(entry: Entry) -> str:
    data = {"tech": entry.tech, "command": entry.command}
    if entry.description:
        data["description"] = entry.description
    # Each entry is serialised on its own, deterministically, so untouched entries never change.
    return yaml.safe_dump([data], sort_keys=False, allow_unicode=True, width=10**6)


def save(path: Path, entries: list[Entry]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER + "".join(_dump(e) for e in entries), encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot write {path}: {exc}") from exc


def settings_path() -> Path:
    return config_dir() / "settings.yaml"


def load_settings() -> dict[str, str]:
    try:
        data = yaml.safe_load(settings_path().read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def save_setting(key: str, value: str) -> None:
    data = load_settings()
    data[key] = value
    try:
        settings_path().parent.mkdir(parents=True, exist_ok=True)
        settings_path().write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot write {settings_path()}: {exc}") from exc
