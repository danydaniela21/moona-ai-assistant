"""Recibe una instantánea local por proceso de Chrome Native Messaging."""

from __future__ import annotations

import json
import re
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from moona_connect_state import MAX_FRAME, connect_directory, parse_snapshot, store_snapshot

HOST_NAME = "com.moona.connect"


def authorize(directory: Path, origin: str) -> None:
    manifest = json.loads((directory / f"{HOST_NAME}.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"chrome-extension://[a-p]{32}/", origin):
        raise ValueError("Invalid extension origin")
    if manifest.get("name") != HOST_NAME or manifest.get("allowed_origins") != [origin]:
        raise ValueError("Unauthorized extension origin")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate field")
    return result


def read_message(source: BinaryIO) -> object:
    header = source.read(4)
    if len(header) != 4:
        raise ValueError("Incomplete header")
    length = struct.unpack("<I", header)[0]
    if not 0 < length <= MAX_FRAME:
        raise ValueError("Invalid message length")
    payload = source.read(length)
    if len(payload) != length:
        raise ValueError("Incomplete message")
    return json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object)


def main(origin: str, source: BinaryIO, output: BinaryIO, directory: Path) -> int:
    try:
        authorize(directory, origin)
        message = read_message(source)
        if not isinstance(message, dict) or message.keys() != {"indicators"}:
            raise ValueError("Invalid message")
        rows = parse_snapshot(message["indicators"], datetime.now(timezone.utc))
        store_snapshot(directory / "indicators.db", rows)
    except (AttributeError, OSError, ValueError, sqlite3.Error, RecursionError):
        # Nunca reenviar datos del navegador ni detalles de la máquina.
        response = b'{"ok":false}'
    else:
        response = b'{"ok":true}'
    output.write(struct.pack("<I", len(response)) + response)
    output.flush()
    return 0 if response == b'{"ok":true}' else 1


if __name__ == "__main__":
    # Los streams binarios de Python mantienen el framing sin conversión de saltos de línea.
    origin = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit(main(origin, sys.stdin.buffer, sys.stdout.buffer, connect_directory()))
