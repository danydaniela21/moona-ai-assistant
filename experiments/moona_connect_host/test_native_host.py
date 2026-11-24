import json
import os
import struct
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from moona_connect_state import MAX_FRAME, PLATFORMS, read_social_indicators

ORIGIN = "chrome-extension://" + "a" * 32 + "/"


class NativeHostTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.local_app_data = Path(temporary.name)
        self.directory = self.local_app_data / "MOONA" / "Connect"
        self.directory.mkdir(parents=True)
        self.manifest = self.directory / "com.moona.connect.json"
        self.manifest.write_text(json.dumps({
            "name": "com.moona.connect",
            "allowed_origins": [ORIGIN],
        }), encoding="utf-8")
        self.database = self.directory / "indicators.db"
        self.now = datetime.now(timezone.utc)

    def snapshot(self, now=None):
        stamp = (now or self.now).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return {"indicators": [
            {"platform": platform, "state": state, "value": value, "updated_at": stamp}
            for platform, (state, value) in zip(
                PLATFORMS, (("observed", 0), ("unknown", None), ("lower_bound", 9), ("no_tab", None))
            )
        ]}

    def run_host(self, data=None, origin=ORIGIN, frame=None):
        if frame is None:
            payload = json.dumps(data).encode("utf-8")
            frame = struct.pack("<I", len(payload)) + payload
        exe = os.environ.get("MOONA_TEST_HOST_EXE")
        command = [exe] if exe else [sys.executable, "-m", "experiments.moona_connect_host.native_host"]
        process = subprocess.run(
            [*command, origin, "--parent-window=0"], input=frame, capture_output=True, timeout=10,
            env={**os.environ, "LOCALAPPDATA": str(self.local_app_data)},
        )
        size, = struct.unpack("<I", process.stdout[:4])
        self.assertEqual(len(process.stdout), size + 4)
        return process.returncode, json.loads(process.stdout[4:])

    def test_binary_round_trip_and_freshness(self):
        self.assertEqual(self.run_host(self.snapshot()), (0, {"ok": True}))
        indicators = read_social_indicators(self.database, self.now)
        self.assertEqual(indicators["instagram"].value, 0)
        self.assertEqual(indicators["facebook"].state, "unknown")
        self.assertIsNone(indicators["facebook"].value)
        self.assertEqual(indicators["whatsapp"].state, "lower_bound")
        self.assertEqual(indicators["linkedin"].state, "no_tab")
        for minutes, state in [(2, "stale"), (5, "disconnected")]:
            row = read_social_indicators(self.database, self.now + timedelta(minutes=minutes))["instagram"]
            self.assertEqual(row.state, state)
            self.assertIsNone(row.value)

    def test_rejects_other_origins_and_multiple_authorized_ids(self):
        wrong = ORIGIN.replace("a", "b")
        self.assertEqual(self.run_host(self.snapshot(), origin=wrong), (1, {"ok": False}))
        self.manifest.write_text(json.dumps({
            "name": "com.moona.connect", "allowed_origins": [ORIGIN, wrong],
        }), encoding="utf-8")
        self.assertEqual(self.run_host(self.snapshot()), (1, {"ok": False}))
        self.assertFalse(self.database.exists())

    def test_rejects_unapproved_fields_partial_frames_and_fabricated_zero(self):
        snapshot = self.snapshot()
        snapshot["indicators"][0]["title"] = "fixture"
        self.assertEqual(self.run_host(snapshot), (1, {"ok": False}))
        snapshot = self.snapshot()
        snapshot["indicators"][1]["value"] = 0
        self.assertEqual(self.run_host(snapshot), (1, {"ok": False}))
        for frame in [b"", struct.pack("<I", MAX_FRAME + 1), struct.pack("<I", 20) + b"x"]:
            self.assertEqual(self.run_host(frame=frame), (1, {"ok": False}))
        self.assertFalse(self.database.exists())

    def test_older_snapshot_cannot_replace_a_fresh_snapshot(self):
        self.assertEqual(self.run_host(self.snapshot()), (0, {"ok": True}))
        old = self.snapshot(self.now - timedelta(minutes=1))
        old["indicators"][0]["value"] = 10
        self.assertEqual(self.run_host(old), (0, {"ok": True}))
        self.assertEqual(read_social_indicators(self.database, self.now)["instagram"].value, 0)

    def test_missing_database_is_disconnected(self):
        self.assertEqual(
            {row.state for row in read_social_indicators(self.database, self.now).values()},
            {"disconnected"},
        )
        self.assertFalse(self.database.exists())

    def test_social_hub_renders_localized_states_alongside_existing_links(self):
        from streamlit.testing.v1 import AppTest

        self.assertEqual(self.run_host(self.snapshot()), (0, {"ok": True}))
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.local_app_data)}):
            for language, unknown, no_tab in [("es", "Desconocido", "Sin pestaña"), ("en", "Unknown", "No tab")]:
                app = AppTest.from_string(
                    "import streamlit as st\n"
                    "from social_hub import renderizar_social_hub\n"
                    "with st.sidebar:\n"
                    f"    renderizar_social_hub({language!r})\n"
                ).run()
                self.assertFalse(app.exception)
                html = app.sidebar.get("html")[0].proto.body
                self.assertIn(">0</span>", html)
                self.assertIn(">9+</span>", html)
                self.assertIn(f">{unknown}</span>", html)
                self.assertIn(f">{no_tab}</span>", html)
                self.assertNotIn("https://outlook.live.com/mail/", html)
                self.assertEqual(html.count('target="_blank"'), 4)
                self.assertEqual(html.count('class="notificaciones"'), 4)
