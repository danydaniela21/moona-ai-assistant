"""OAuth web seguro y acceso de solo lectura a Gmail y Google Calendar.

La transacción OAuth pendiente se guarda brevemente fuera de la sesión de
Streamlit, porque el callback puede crear un nuevo WebSocket. No se registra
ni se muestra ningún secreto, código de autorización o token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hmac
import json
from pathlib import Path
import time
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError


# Estos son los únicos permisos solicitados: ambos son estrictamente de lectura.
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
)
OAUTH_TTL_SECONDS = 600


class GoogleServiceError(Exception):
    """Error controlado de OAuth, permisos o comunicación con Google."""


@dataclass(frozen=True)
class GoogleConfig:
    """Rutas locales a credenciales y token, nunca incluidas en Git."""

    credentials_file: Path
    token_file: Path
    pending_file: Path
    redirect_uri: str = "http://localhost:8501"


class GoogleOAuthManager:
    """Gestiona Authorization Code, state y PKCE para el cliente web local."""

    def __init__(self, config: GoogleConfig) -> None:
        self.config = config

    @property
    def conectado(self) -> bool:
        return self.config.token_file.is_file()

    def iniciar(self) -> str:
        """Crea una URL OAuth con state aleatorio y desafío PKCE S256."""

        if not self.config.credentials_file.is_file():
            raise GoogleServiceError(
                f"No se encontró el archivo OAuth en {self.config.credentials_file}."
            )
        try:
            pendiente = self._leer_pendiente()
            if pendiente and time.time() - float(pendiente.get("created_at", 0)) <= OAUTH_TTL_SECONDS:
                url_existente = pendiente.get("authorization_url")
                if isinstance(url_existente, str):
                    return url_existente

            flow = Flow.from_client_secrets_file(
                str(self.config.credentials_file),
                scopes=list(SCOPES),
                redirect_uri=self.config.redirect_uri,
                autogenerate_code_verifier=True,
            )
            authorization_url, state = flow.authorization_url(
                access_type="offline",
                prompt="consent",
                include_granted_scopes="false",
            )
            self._guardar_pendiente(
                {
                    "state": state,
                    "code_verifier": flow.code_verifier,
                    "created_at": time.time(),
                    "authorization_url": authorization_url,
                }
            )
            return authorization_url
        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleServiceError(
                "No se pudo iniciar OAuth con Google. Verifica credentials.json y la redirect URI."
            ) from exc

    def completar(self, respuesta: dict[str, str]) -> None:
        """Valida state y PKCE, consume el código una sola vez y guarda el token."""

        if respuesta.get("error"):
            self._eliminar_pendiente()
            raise GoogleServiceError("Google canceló o rechazó la autorización solicitada.")
        state_recibido = respuesta.get("state", "")
        code = respuesta.get("code", "")
        pendiente = self._leer_pendiente()
        if not pendiente or not state_recibido:
            raise GoogleServiceError("La transacción OAuth no existe o ya fue utilizada.")
        state_esperado = str(pendiente.get("state", ""))
        if not hmac.compare_digest(state_recibido, state_esperado):
            raise GoogleServiceError("La validación de seguridad OAuth falló (state no coincide).")
        if time.time() - float(pendiente.get("created_at", 0)) > OAUTH_TTL_SECONDS:
            self._eliminar_pendiente()
            raise GoogleServiceError("La autorización OAuth expiró. Inicia la conexión nuevamente.")
        if not code:
            raise GoogleServiceError("Google no devolvió un código de autorización válido.")

        # El estado ya fue validado: se consume incluso si el canje posterior falla.
        self._eliminar_pendiente()
        try:
            flow = Flow.from_client_secrets_file(
                str(self.config.credentials_file),
                scopes=list(SCOPES),
                state=state_esperado,
                code_verifier=str(pendiente.get("code_verifier", "")),
                redirect_uri=self.config.redirect_uri,
            )
            flow.fetch_token(code=code)
            credenciales = flow.credentials
            if not credenciales.has_scopes(list(SCOPES)):
                raise GoogleServiceError("No se concedieron todos los permisos de lectura requeridos.")
            self._guardar_token(credenciales)
        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleServiceError(
                "No fue posible canjear la autorización. Comprueba la redirect URI y vuelve a intentarlo."
            ) from exc

    def credenciales(self) -> Credentials:
        """Carga y renueva el token local sin ampliar sus permisos."""

        if not self.config.token_file.is_file():
            raise GoogleServiceError("Conecta tu cuenta personal de Google para continuar.")
        try:
            credenciales = Credentials.from_authorized_user_file(
                str(self.config.token_file), scopes=list(SCOPES)
            )
            if credenciales.expired and credenciales.refresh_token:
                credenciales.refresh(Request())
                self._guardar_token(credenciales)
        except (OSError, ValueError, RefreshError) as exc:
            raise GoogleServiceError(
                "El token de Google no es válido o expiró. Desconecta la cuenta y autoriza nuevamente."
            ) from exc
        if not credenciales.valid:
            raise GoogleServiceError("La sesión de Google no es válida. Autoriza nuevamente.")
        return credenciales

    def desconectar(self) -> None:
        """Elimina el token local; no revoca permisos en la cuenta de Google."""

        try:
            self.config.token_file.unlink(missing_ok=True)
            self.config.pending_file.unlink(missing_ok=True)
        except OSError as exc:
            raise GoogleServiceError("No fue posible eliminar el token local.") from exc

    def _guardar_token(self, credenciales: Credentials) -> None:
        """Persiste el token fuera del repositorio con acceso restringido al usuario."""

        try:
            self.config.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.config.token_file.write_text(credenciales.to_json(), encoding="utf-8")
        except OSError as exc:
            raise GoogleServiceError("No fue posible guardar el token OAuth local.") from exc

    def _leer_pendiente(self) -> dict[str, Any] | None:
        """Lee la transacción temporal sin exponer su contenido."""

        if not self.config.pending_file.is_file():
            return None
        try:
            return json.loads(self.config.pending_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _guardar_pendiente(self, pendiente: dict[str, Any]) -> None:
        """Persiste state y verifier fuera de Git durante un máximo de diez minutos."""

        try:
            self.config.pending_file.parent.mkdir(parents=True, exist_ok=True)
            self.config.pending_file.write_text(json.dumps(pendiente), encoding="utf-8")
        except OSError as exc:
            raise GoogleServiceError("No fue posible guardar la transacción OAuth temporal.") from exc

    def _eliminar_pendiente(self) -> None:
        try:
            self.config.pending_file.unlink(missing_ok=True)
        except OSError as exc:
            raise GoogleServiceError("No fue posible cerrar la transacción OAuth temporal.") from exc


class GoogleWorkspaceService:
    """Agrupa las consultas reales de Gmail y Calendar en modo lectura."""

    def __init__(self, oauth: GoogleOAuthManager) -> None:
        self.oauth = oauth

    @property
    def conectado(self) -> bool:
        return self.oauth.conectado

    def iniciar_autenticacion(self) -> str:
        return self.oauth.iniciar()

    def completar_autenticacion(self, respuesta: dict[str, str]) -> None:
        self.oauth.completar(respuesta)

    def desconectar(self) -> None:
        self.oauth.desconectar()

    def _cliente(self, api: str, version: str) -> Resource:
        try:
            return build(api, version, credentials=self.oauth.credenciales(), cache_discovery=False)
        except (HttpError, OSError) as exc:
            raise GoogleServiceError("No fue posible iniciar la conexión con Google.") from exc

    @staticmethod
    def _ejecutar(solicitud: Any) -> dict[str, Any]:
        try:
            return solicitud.execute()
        except HttpError as exc:
            codigo = getattr(exc.resp, "status", None)
            if codigo in (401, 403):
                raise GoogleServiceError(
                    "Google rechazó el acceso. Verifica que Gmail API y Google Calendar API estén "
                    "habilitadas y que los permisos de solo lectura estén autorizados."
                ) from exc
            raise GoogleServiceError(f"Google devolvió un error al consultar los datos ({codigo or 'desconocido'}).") from exc
        except OSError as exc:
            raise GoogleServiceError("No fue posible comunicarse con Google.") from exc

    def perfil(self) -> dict[str, Any]:
        """Obtiene la dirección real de la cuenta mediante Gmail API."""

        gmail = self._cliente("gmail", "v1")
        return self._ejecutar(gmail.users().getProfile(userId="me"))

    def correos(self, busqueda: str = "", limite: int = 10) -> list[dict[str, Any]]:
        """Busca mensajes con la sintaxis oficial de Gmail y devuelve sus metadatos."""

        gmail = self._cliente("gmail", "v1")
        resultado = self._ejecutar(
            gmail.users().messages().list(
                userId="me",
                q=busqueda.strip() or None,
                maxResults=max(1, min(limite, 25)),
            )
        )
        mensajes: list[dict[str, Any]] = []
        for referencia in resultado.get("messages", []):
            mensaje = self._ejecutar(
                gmail.users().messages().get(
                    userId="me",
                    id=referencia["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
            )
            cabeceras = {
                item.get("name", "").lower(): item.get("value", "")
                for item in mensaje.get("payload", {}).get("headers", [])
            }
            fecha = cabeceras.get("date", "")
            try:
                fecha_iso = parsedate_to_datetime(fecha).isoformat()
            except (TypeError, ValueError):
                fecha_iso = datetime.fromtimestamp(
                    int(mensaje.get("internalDate", "0")) / 1000, tz=timezone.utc
                ).isoformat()
            mensajes.append(
                {
                    "subject": cabeceras.get("subject") or "Sin asunto",
                    "from": cabeceras.get("from") or "Remitente desconocido",
                    "received": fecha_iso,
                    "unread": "UNREAD" in mensaje.get("labelIds", []),
                }
            )
        return mensajes

    def proximos_eventos(self, limite: int = 10) -> list[dict[str, Any]]:
        """Devuelve los próximos eventos del calendario principal."""

        calendar = self._cliente("calendar", "v3")
        ahora = datetime.now(timezone.utc).isoformat()
        resultado = self._ejecutar(
            calendar.events().list(
                calendarId="primary",
                timeMin=ahora,
                maxResults=max(1, min(limite, 25)),
                singleEvents=True,
                orderBy="startTime",
            )
        )
        return list(resultado.get("items", []))
