"""Regresión de OAuth y consultas de solo lectura con datos de prueba."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from httplib2 import Response
from streamlit.testing.v1 import AppTest

from google_service import (
    MENSAJE_RECONEXION,
    SCOPES,
    GoogleAuthenticationError,
    GoogleConfig,
    GoogleOAuthManager,
    GoogleWorkspaceService,
)
from i18n import translate


class GoogleAuthenticationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.config = GoogleConfig(root / "credentials.json", root / "token.json", root / "pending.json")
        self.config.credentials_file.write_text("{}", encoding="utf-8")
        self.manager = GoogleOAuthManager(self.config)

    def token(self, *, expired=False, refresh_token="test-refresh"):
        expiry = datetime.now(timezone.utc) + timedelta(hours=-1 if expired else 1)
        self.config.token_file.write_text(json.dumps({
            "token": "test-access",
            "refresh_token": refresh_token,
            "client_id": "test-client",
            "client_secret": "test-client-secret",
            "scopes": list(SCOPES),
            "expiry": expiry.isoformat().replace("+00:00", "Z"),
        }), encoding="utf-8")

    def test_renewal_uses_refresh_token_and_persists_the_new_access_token(self):
        self.token(expired=True)
        response = Mock(status=200, data=b'{"access_token":"new-access","expires_in":3600}')
        transport = Mock(return_value=response)
        with patch("google_service.Request", return_value=transport):
            self.assertTrue(self.manager.conectado)
            self.assertEqual(self.manager.credenciales().token, "new-access")
            self.assertTrue(self.manager.conectado)
            self.assertTrue(GoogleOAuthManager(self.config).conectado)
        transport.assert_called_once()
        saved = json.loads(self.config.token_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["token"], "new-access")
        self.assertEqual(saved["refresh_token"], "test-refresh")
        self.assertFalse(list(self.config.token_file.parent.glob("*.tmp")))

    def test_missing_refresh_token_and_corrupt_token_are_not_connections(self):
        self.token(refresh_token=None)
        self.assertFalse(self.manager.conectado)
        self.config.token_file.write_text("[]", encoding="utf-8")
        self.assertFalse(GoogleOAuthManager(self.config).conectado)

    def test_google_rejection_and_transport_failure_do_not_retry_in_the_same_run(self):
        for failure in (RefreshError("invalid_grant"), TransportError("offline")):
            with self.subTest(failure=type(failure).__name__):
                self.token(expired=True)
                manager = GoogleOAuthManager(self.config)
                with patch("google_service.Credentials.refresh", side_effect=failure) as refresh:
                    self.assertFalse(manager.conectado)
                    self.assertFalse(manager.conectado)
                    self.assertEqual(str(manager.error_autenticacion), MENSAJE_RECONEXION)
                    refresh.assert_called_once()

    def test_gmail_search_and_calendar_remain_read_only(self):
        self.token()
        servicio = GoogleWorkspaceService(self.manager)
        gmail, calendar = Mock(), Mock()
        messages = gmail.users.return_value.messages.return_value
        messages.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
        messages.get.return_value.execute.return_value = {
            "labelIds": ["UNREAD"],
            "internalDate": "1700000000000",
            "payload": {"headers": [{"name": "Subject", "value": "Fixture subject"}]},
        }
        calendar.events.return_value.list.return_value.execute.return_value = {
            "items": [{"summary": "Fixture event"}],
        }
        with patch("google_service.build", side_effect=[gmail, calendar]):
            self.assertEqual(servicio.correos(" is:unread ")[0]["subject"], "Fixture subject")
            self.assertEqual(servicio.proximos_eventos()[0]["summary"], "Fixture event")
        self.assertEqual(messages.list.call_args.kwargs["q"], "is:unread")
        self.assertEqual(messages.get.call_args.kwargs["format"], "metadata")
        self.assertEqual(calendar.events.return_value.list.call_args.kwargs["calendarId"], "primary")

    def test_api_401_is_an_authentication_failure(self):
        self.token()
        gmail = Mock()
        gmail.users.return_value.getProfile.return_value.execute.side_effect = HttpError(
            Response({"status": "401"}), b"{}"
        )
        with patch("google_service.build", return_value=gmail):
            with self.assertRaises(GoogleAuthenticationError):
                GoogleWorkspaceService(self.manager).perfil()

    def test_transport_refresh_during_a_query_is_persisted(self):
        self.token()
        servicio = GoogleWorkspaceService(self.manager)
        gmail = Mock()

        def execute():
            self.manager.credenciales().token = "transport-access"
            return {"emailAddress": "fixture@example.test"}

        gmail.users.return_value.getProfile.return_value.execute.side_effect = execute
        with patch("google_service.build", return_value=gmail):
            self.assertIn("emailAddress", servicio.perfil())
        self.assertEqual(GoogleOAuthManager(self.config).credenciales().token, "transport-access")

    def test_api_rejection_clears_the_connected_indicator_after_rerun(self):
        import app

        self.token()
        gmail = Mock()
        gmail.users.return_value.getProfile.return_value.execute.return_value = {}
        gmail.users.return_value.messages.return_value.list.return_value.execute.side_effect = HttpError(
            Response({"status": "401"}), b"{}"
        )
        with (
            patch.object(app, "GoogleConfig", return_value=self.config),
            patch.object(app, "cargar_preferencias", return_value={"idioma": "en", "nombre": "Test"}),
            patch("google_service.build", return_value=gmail),
            patch.object(GoogleOAuthManager, "iniciar", return_value="https://accounts.google.com/"),
        ):
            at = AppTest.from_string("import app\napp.main()", default_timeout=30)
            at.session_state["seccion_nav"] = "Correo Gmail"
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual([element.value for element in at.error], [translate(MENSAJE_RECONEXION, "en")])
            self.assertTrue(any("Local mode" in element.proto.body for element in at.get("html")))
            self.assertFalse(any("Google connected" in element.proto.body for element in at.get("html")))
            rejected = self.config.token_file.stat().st_mtime_ns
            self.token()
            os.utime(self.config.token_file, ns=(rejected, rejected + 1_000_000_000))
            request = gmail.users.return_value.messages.return_value.list.return_value
            request.execute.side_effect = None
            request.execute.return_value = {}
            at.run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error)
            self.assertTrue(any("Google connected" in element.proto.body for element in at.get("html")))

    def test_google_views_render_one_localized_error_and_the_reconnect_link(self):
        import app

        self.token(expired=True)
        for language in ("es", "en"):
            for section in ("Correo Gmail", "Calendario"):
                with (
                    self.subTest(language=language, section=section),
                    patch.object(app, "GoogleConfig", return_value=self.config),
                    patch.object(app, "cargar_preferencias", return_value={"idioma": language, "nombre": "Test"}),
                    patch("google_service.Credentials.refresh", side_effect=RefreshError("invalid_grant")) as refresh,
                    patch.object(GoogleOAuthManager, "iniciar", return_value="https://accounts.google.com/"),
                ):
                    at = AppTest.from_string("import app\napp.main()", default_timeout=30)
                    at.session_state["seccion_nav"] = section
                    at.run()
                    self.assertFalse(at.exception)
                    self.assertEqual([element.value for element in at.error], [translate(MENSAJE_RECONEXION, language)])
                    self.assertEqual(at.get("link_button")[0].proto.label,
                                     translate("Reconectar mi cuenta de Google", language))
                    self.assertTrue(any(translate("Modo local", language) in element.proto.body
                                        for element in at.get("html")))
                    refresh.assert_called_once()
