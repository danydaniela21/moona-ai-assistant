"""Contrato y almacenamiento local compartidos entre MOONA y el host de Chrome."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLATFORMS = ("instagram", "facebook", "whatsapp", "linkedin")
NUMBER_STATES = {"observed", "lower_bound"}
OTHER_STATES = {"unknown", "no_tab", "unauthorized", "unavailable"}
MAX_FRAME = 4096
STALE_AFTER = timedelta(seconds=120)
DISCONNECTED_AFTER = timedelta(minutes=5)
CLOCK_SKEW = timedelta(seconds=10)


@dataclass(frozen=True)
class Indicator:
    platform: str
    value: int | None
    state: str
    updated_at: str | None = None


def connect_directory() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MOONA" / "Connect"


def parse_snapshot(data: object, now: datetime) -> list[Indicator]:
    if not isinstance(data, list) or len(data) != len(PLATFORMS):
        raise ValueError("Invalid snapshot")

    indicators = []
    for row in data:
        if not isinstance(row, dict) or row.keys() != {"platform", "value", "state", "updated_at"}:
            raise ValueError("Invalid indicator fields")
        platform, value, state, updated_at = (row[key] for key in ("platform", "value", "state", "updated_at"))
        if platform not in PLATFORMS or not isinstance(state, str):
            raise ValueError("Invalid platform or state")
        if state in NUMBER_STATES:
            minimum = 1 if state == "lower_bound" else 0
            if type(value) is not int or not minimum <= value <= 999_999_999:
                raise ValueError("Invalid numeric indicator")
        elif state not in OTHER_STATES or value is not None:
            raise ValueError("Invalid nonnumeric indicator")
        if not isinstance(updated_at, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", updated_at
        ):
            raise ValueError("Invalid update timestamp")
        if datetime.fromisoformat(updated_at.replace("Z", "+00:00")) > now + CLOCK_SKEW:
            raise ValueError("Timestamp is in the future")
        indicators.append(Indicator(platform, value, state, updated_at))

    if {row.platform for row in indicators} != set(PLATFORMS):
        raise ValueError("Duplicate platform")
    if len({row.updated_at for row in indicators}) != 1:
        raise ValueError("Inconsistent snapshot timestamp")
    return indicators


def store_snapshot(path: Path, rows: list[Indicator]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=3)) as connection, connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS indicators (
                platform TEXT PRIMARY KEY, value INTEGER, state TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        connection.executemany(
            """INSERT INTO indicators (platform, value, state, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                value = excluded.value, state = excluded.state, updated_at = excluded.updated_at
            WHERE excluded.updated_at >= indicators.updated_at""",
            [(row.platform, row.value, row.state, row.updated_at) for row in rows],
        )


def read_social_indicators(
    path: Path | None = None, now: datetime | None = None
) -> dict[str, Indicator]:
    path = path if path is not None else connect_directory() / "indicators.db"
    now = now if now is not None else datetime.now(timezone.utc)
    disconnected = {platform: Indicator(platform, None, "disconnected") for platform in PLATFORMS}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25)) as connection:
            rows = connection.execute("SELECT platform, value, state, updated_at FROM indicators").fetchall()
        snapshot = parse_snapshot(
            [dict(zip(("platform", "value", "state", "updated_at"), row)) for row in rows], now
        )
    except (sqlite3.Error, ValueError, OSError):
        return disconnected

    result = {}
    for row in snapshot:
        updated_at = datetime.fromisoformat(row.updated_at.replace("Z", "+00:00"))
        age = now - updated_at
        if age >= DISCONNECTED_AFTER:
            row = Indicator(row.platform, None, "disconnected", row.updated_at)
        elif age >= STALE_AFTER:
            row = Indicator(row.platform, None, "stale", row.updated_at)
        result[row.platform] = row
    return result
