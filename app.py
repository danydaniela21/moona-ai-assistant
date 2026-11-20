"""Interfaz de JARVIS Personal con acceso de solo lectura a Google.

La lógica de OAuth y de las APIs vive en un módulo independiente para mantener
separadas la interfaz, la autenticación y las futuras integraciones.
"""

from dataclasses import dataclass
from datetime import date, datetime
import base64
import hashlib
from html import escape
import json
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import uuid4

import streamlit as st

from academic_documents import (
    ESTADOS_EVALUACION,
    AcademicDocumentError,
    AcademicDocumentRepository,
)
from ai_service import AIService, AIServiceError
from browser_tts import render_auto_voice_response
from database import (
    CATEGORIAS,
    ESTADOS,
    PRIORIDADES,
    DatabaseError,
    TaskDatabase,
)
from i18n import DEFAULT_LANGUAGE, LANGUAGE_LABELS, translate

from google_service import (
    GoogleConfig,
    GoogleOAuthManager,
    GoogleServiceError,
    GoogleWorkspaceService,
)
from voice_service import VoiceServiceError, transcribe_wav
from tts_service import (
    DEFAULT_VOICE,
    ENGLISH_VOICE,
    TTSServiceError,
    synthesize_speech,
)


MOONA_ICON_PATH = Path("assets/moona_robot.png")
MOONA_BACKGROUND_PATH = Path("assets/moona_background2.png")
MOONA_ICON_DATA_URI = (
    "data:image/png;base64,"
    + base64.b64encode(MOONA_ICON_PATH.read_bytes()).decode("ascii")
)
MOONA_BACKGROUND_DATA_URI = (
    "data:image/png;base64,"
    + base64.b64encode(MOONA_BACKGROUND_PATH.read_bytes()).decode("ascii")
)
PREFERENCIAS_FILE = Path(".streamlit/user_preferences.json")
try:
    _IDIOMA_INICIAL = json.loads(
        PREFERENCIAS_FILE.read_text(encoding="utf-8")
    ).get("idioma", DEFAULT_LANGUAGE)
except (OSError, ValueError, TypeError):
    _IDIOMA_INICIAL = DEFAULT_LANGUAGE

# Configuración general de la aplicación.
st.set_page_config(
    page_title=(
        "MOONA · Intelligent Personal Assistant"
        if _IDIOMA_INICIAL == "en"
        else "MOONA · Asistente Personal Inteligente"
    ),
    page_icon=MOONA_ICON_PATH,
    layout="wide",
    initial_sidebar_state="expanded",
)


MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass(frozen=True)
class Seccion:
    """Describe una opción de navegación de la interfaz."""

    nombre: str
    icono: str
    descripcion: str


SECCIONES = (
    Seccion("Asistente", "✦", "Tu centro de consultas inteligentes"),
    Seccion("Correo Gmail", "✉", "Correo personal de Google"),
    Seccion("Calendario", "▦", "Agenda y próximos eventos"),
    Seccion("Tareas y actividades", "✓", "Organización personal, académica y profesional"),
    Seccion("Documentos académicos", "▤", "Archivos Word y Excel de tus actividades"),
)

TAREAS_DB_FILE = Path(".data/jarvis_tasks.db")
DOCUMENTOS_DB_FILE = Path(".data/academic_documents.db")
DOCUMENTOS_DIR = Path(".data/academic_documents")


def aplicar_estilos() -> None:
    """Aplica la identidad visual rosada, oscura y adaptable de MOONA."""

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600&display=swap');

        :root {
            --cyan: #FF1493;
            --cyan-soft: rgba(255, 20, 147, .16);
            --line: rgba(255, 105, 180, .42);
            --muted: #E4BDD3;
            --violet: #190D1F;
        }
        .stApp {
            background-color:#080509;
            background-image:
                linear-gradient(90deg, rgba(8,5,9,.14), rgba(8,5,9,.08) 60%, rgba(8,5,9,.02)),
                url("__MOONA_BACKGROUND__");
            background-size:cover;
            background-position:center top;
            background-repeat:no-repeat;
            background-attachment:fixed;
            color: #FCE7F3;
        }
        [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { position:relative; z-index:1; }
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -.03em; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
            background: transparent;
            border-right: 0;
        }
        [data-testid="stSidebar"] > div:first-child {
            margin:.75rem; padding:1.1rem .7rem 1.2rem; height:calc(100vh - 1.5rem);
            border:1px solid rgba(255,20,147,.82); border-radius:24px;
            background:linear-gradient(165deg,rgba(8,5,9,.82),rgba(25,13,31,.70));
            backdrop-filter:blur(18px) saturate(125%);
            box-shadow:0 0 30px rgba(255,20,147,.08), inset 0 0 35px rgba(255,20,147,.025);
        }
        [data-testid="stSidebar"] .stRadio label {
            border-radius: 14px;
            padding: .72rem .8rem;
            transition: background .2s ease, color .2s ease;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
            background: var(--cyan-soft);
            color: var(--cyan);
        }
        [data-testid="stSidebar"] .stRadio [role="radiogroup"] { gap:.35rem; }
        [data-testid="stSidebar"] .stRadio label > div:first-child { display:none !important; }
        [data-testid="stSidebar"] .stRadio label p { font-size:.94rem; font-weight:600; }
        div[data-testid="stAudioInput"] {
            border:1px solid var(--line); border-radius:14px; padding:.65rem;
            background:rgba(8,5,15,.68); box-shadow:0 0 20px rgba(236,72,153,.10);
            backdrop-filter:blur(14px);
        }
        /* La grabación se envía al detenerla; no se ofrece reproducción previa. */
        div[data-testid="stAudioInput"] audio { display:none !important; }
        .voice-console {
            display:grid; place-items:center; min-height:245px; margin:.8rem 0 1rem;
            border:1px solid var(--line); border-radius:24px;
            background:radial-gradient(circle, rgba(236,72,153,.14), transparent 48%), rgba(8,5,15,.66);
            backdrop-filter:blur(16px);
            overflow:hidden;
        }
        .voice-orb {
            width:132px; height:132px; border-radius:50%; display:grid; place-items:center;
            border:1px solid rgba(255,105,180,.72); color:#FF69B4;
            box-shadow:0 0 30px rgba(255,20,147,.30), inset 0 0 26px rgba(255,105,180,.12);
            position:relative; animation:voicePulse 2s ease-in-out infinite;
        }
        .voice-orb::before, .voice-orb::after {
            content:""; position:absolute; inset:-14px; border:1px solid rgba(244,114,182,.22);
            border-radius:50%; animation:voiceRing 2.4s ease-out infinite;
        }
        .voice-orb::after { animation-delay:1.2s; }
        .voice-orb.processing { animation-duration:.75s; border-style:dashed; }
        .voice-orb.responding { box-shadow:0 0 48px rgba(236,72,153,.48), inset 0 0 30px rgba(244,114,182,.20); }
        .voice-label { margin-top:1.2rem; color:#FBCFE8; font-size:.76rem; letter-spacing:.16em; text-transform:uppercase; text-align:center; }
        @keyframes voicePulse { 50% { transform:scale(.96); opacity:.82; } }
        @keyframes voiceRing { from { transform:scale(.82); opacity:.65; } to { transform:scale(1.24); opacity:0; } }
        .block-container { max-width: 1280px; padding-top: 1.25rem; padding-bottom: 2rem; }
        .brand { display:flex; flex-direction:column; align-items:center; gap:.12rem; margin:0 0 1.35rem; text-align:center; }
        .brand-orb { width:138px; height:138px; object-fit:contain; filter:drop-shadow(0 0 18px rgba(255,20,147,.64)); }
        .brand-name { font:700 1.9rem 'Space Grotesk'; letter-spacing:.1em; text-shadow:0 0 16px rgba(255,20,147,.46); }
        .eyebrow { color:var(--cyan); font-size:.75rem; font-weight:600; letter-spacing:.14em; text-transform:uppercase; }
        .assistant-title {
            margin:.1rem 0 .65rem; font-size:clamp(1.8rem,4vw,2.65rem);
            letter-spacing:.04em !important; color:#FCE7F3;
            text-shadow:0 0 18px rgba(255,20,147,.32);
        }
        .hero { padding: .25rem 0 .75rem; }
        .hero h1 { font-size:clamp(2rem, 5vw, 3.6rem); margin:.2rem 0 .3rem; line-height:1.05; }
        .hero p { color:var(--muted); font-size:clamp(.95rem, 2vw, 1.08rem); margin:0; }
        .status-row { display:flex; gap:.65rem; flex-wrap:wrap; margin-top:.75rem; }
        .status-pill {
            border:1px solid var(--line); background:rgba(49,15,39,.58); border-radius:999px;
            padding:.42rem .75rem; color:#F5C6DD; font-size:.76rem;
        }
        .status-dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--cyan); margin-right:.45rem; box-shadow:0 0 8px var(--cyan); }
        .empty-state {
            margin-top:.6rem; padding:clamp(1.35rem, 3vw, 2.1rem);
            border:1px solid rgba(255,105,180,.36); border-radius:24px;
            background:linear-gradient(135deg,rgba(8,5,9,.73),rgba(25,13,31,.60)); backdrop-filter:blur(16px);
        }
        .welcome-grid { display:grid; grid-template-columns:180px 1fr; gap:1.6rem; align-items:center; text-align:left; }
        .welcome-robot { width:170px; filter:drop-shadow(0 10px 16px rgba(255,20,147,.40)); }
        .welcome-copy { border-left:1px solid #FF1493; padding-left:1.8rem; }
        .welcome-copy h2 { margin:0 0 .55rem; font-size:clamp(1.55rem,3vw,2.35rem); }
        .welcome-copy p { color:#FCE7F3; margin:0; font-size:1.02rem; line-height:1.55; }
        .quick-label { margin:.95rem 0 .25rem; color:#E4BDD3; font-size:.78rem; letter-spacing:.08em; text-transform:uppercase; }
        .data-card {
            margin:.7rem 0; padding:1rem 1.15rem; border:1px solid var(--line);
            border-radius:14px; background:rgba(8,5,15,.68); backdrop-filter:blur(14px);
        }
        .data-card h3 { margin:0 0 .35rem; font-size:1rem; }
        .data-meta { color:var(--muted); font-size:.79rem; line-height:1.55; }
        .unread { color:var(--cyan); font-size:.68rem; font-weight:700; letter-spacing:.1em; }
        .account-box { margin:1rem 0; padding:.8rem 1rem; border-left:2px solid var(--cyan); background:var(--cyan-soft); border-radius:0 10px 10px 0; }
        .task-card {
            margin:.35rem 0 .75rem; padding:1rem 1.1rem; border:1px solid var(--line);
            border-radius:14px; background:rgba(8,5,15,.68); backdrop-filter:blur(14px);
        }
        .task-card.overdue {
            border-color:rgba(255,20,147,.58); box-shadow:inset 3px 0 0 #FF1493;
            background:linear-gradient(90deg, rgba(255,20,147,.11), rgba(8,5,9,.72) 35%);
        }
        .task-title { font:600 1rem 'Space Grotesk'; color:#FCE7F3; margin-bottom:.35rem; }
        .task-description { color:#E8BDD4; font-size:.86rem; line-height:1.55; margin:.5rem 0; }
        .task-badge {
            display:inline-block; margin:.25rem .35rem 0 0; padding:.22rem .55rem;
            border:1px solid var(--line); border-radius:999px; color:#DCB1CA; font-size:.7rem;
        }
        .task-overdue { color:#FF69B4; font-size:.72rem; font-weight:700; letter-spacing:.08em; }
        [data-testid="stChatMessage"] {
            border:1px solid var(--line); border-radius:16px;
            background:rgba(8,5,9,.70); padding:.35rem .65rem; backdrop-filter:blur(14px);
        }
        .sidebar-footer { color:#9F6B89; font-size:.68rem; padding:.75rem .4rem; letter-spacing:.06em; }
        div[data-testid="stTextInput"] input {
            background:rgba(8,5,15,.78); border:1px solid var(--line); color:#FCE7F3; border-radius:10px;
        }
        div[data-testid="stTextInput"] input:focus { border-color:var(--cyan); box-shadow:0 0 0 1px var(--cyan); }
        .stButton > button, .stDownloadButton > button, .stLinkButton > a, [data-testid="stFormSubmitButton"] > button {
            border:1px solid rgba(244,114,182,.32); border-radius:10px;
            background:linear-gradient(135deg, rgba(236,72,153,.20), rgba(48,20,63,.55));
            color:#FCE7F3; box-shadow:0 7px 22px rgba(80,10,49,.15);
        }
        .stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover {
            border-color:#FF69B4; color:#FCE7F3; box-shadow:0 0 18px rgba(255,20,147,.26);
        }
        [data-baseweb="select"] > div, [data-testid="stTextArea"] textarea,
        [data-testid="stFileUploaderDropzone"], [data-testid="stDateInput"] input {
            background:rgba(8,5,15,.78) !important; border-color:var(--line) !important; color:#FCE7F3 !important;
        }
        table { border-color:var(--line) !important; }
        th { background:rgba(236,72,153,.18) !important; color:#FCE7F3 !important; }
        td { border-color:var(--line) !important; }
        /* Neutraliza el rojo predeterminado en todos los controles interactivos. */
        *:focus-visible { outline-color:#FF1493 !important; }
        input[type="checkbox"], input[type="radio"] { accent-color:#FF1493 !important; }
        button[kind="primary"], button[data-testid="baseButton-primary"],
        [data-testid="stFormSubmitButton"] button[kind="primary"] {
            background:#FF1493 !important; border-color:#FF1493 !important; color:#FCE7F3 !important;
        }
        button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
            background:#FF69B4 !important; border-color:#FF69B4 !important;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"],
        [data-testid="stSegmentedControl"] button[aria-checked="true"],
        [data-testid="stSegmentedControl"] [data-selected="true"],
        [role="tab"][aria-selected="true"] {
            background:linear-gradient(135deg,#FF1493,#C00070) !important;
            border-color:#FF69B4 !important; color:#FCE7F3 !important;
            box-shadow:0 0 16px rgba(236,72,153,.30) !important;
        }
        [data-testid="stSegmentedControl"] button:hover,
        [data-testid="stAudioInput"] button:hover,
        [data-testid="stChatInput"] button:hover {
            border-color:#FF1493 !important; color:#FF69B4 !important;
        }
        [data-testid="stSidebar"] label:has(input:checked),
        label:has(input[type="checkbox"]:checked) {
            color:#FCE7F3 !important; accent-color:#FF1493 !important;
        }
        [data-testid="stSidebar"] label:has(input:checked) {
            background:linear-gradient(90deg,rgba(255,20,147,.88),rgba(190,24,93,.72)) !important;
            box-shadow:0 0 18px rgba(255,20,147,.30);
        }
        [data-baseweb="checkbox"] [aria-checked="true"],
        [data-baseweb="radio"] [aria-checked="true"] {
            background-color:#FF1493 !important; border-color:#FF1493 !important;
        }
        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] > div,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextArea"] textarea {
            background:rgba(8,5,15,.78) !important; border-color:var(--line) !important;
            color:#FCE7F3 !important;
        }
        [data-testid="stChatInput"]:focus-within,
        [data-testid="stTextInput"]:focus-within,
        [data-testid="stTextArea"]:focus-within,
        [data-baseweb="select"]:focus-within,
        [data-testid="stAudioInput"]:focus-within {
            border-color:#FF1493 !important; box-shadow:0 0 0 1px #FF1493 !important;
        }
        [data-baseweb="tag"] { background:#30143F !important; color:#FCE7F3 !important; }
        [data-testid="stChatInput"] { border:1px solid #FF1493 !important; border-radius:22px !important; overflow:hidden; }
        [data-testid="stChatInput"] button { border-radius:50% !important; color:#FCE7F3 !important; background:#FF1493 !important; }
        [data-testid="stExpander"] { border:1px solid rgba(255,20,147,.72) !important; border-radius:18px !important; background:rgba(8,5,9,.66) !important; }
        hr { border-color:rgba(255,105,180,.20) !important; }
        @media (max-width: 768px) {
            .block-container { padding:1.2rem 1rem 2rem; }
            .hero { padding-top:.2rem; }
            .welcome-grid { grid-template-columns:1fr; text-align:center; }
            .welcome-robot { width:130px; margin:auto; }
            .welcome-copy { border-left:0; border-top:1px solid #FF1493; padding:1rem 0 0; }
        }
        </style>
        """.replace("__MOONA_BACKGROUND__", MOONA_BACKGROUND_DATA_URI),
        unsafe_allow_html=True,
    )


def idioma_actual() -> str:
    """Devuelve el idioma activo de la interfaz."""

    return str(st.session_state.get("idioma", DEFAULT_LANGUAGE))


def tr(texto: str, **valores: object) -> str:
    """Atajo de traducción para la sesión actual."""

    return translate(texto, idioma_actual(), **valores)


def fecha_localizada() -> str:
    """Devuelve la fecha local sin depender de la configuración del sistema."""

    ahora = datetime.now()
    if idioma_actual() == "en":
        dias = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        meses = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
        return f"{dias[ahora.weekday()]}, {meses[ahora.month - 1]} {ahora.day}, {ahora.year}"
    return f"{DIAS[ahora.weekday()]}, {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}".capitalize()


def saludo_segun_hora() -> str:
    """Selecciona un saludo usando la hora local del dispositivo."""

    hora = datetime.now().hour
    if hora < 12:
        return tr("Buenos días")
    if hora < 19:
        return tr("Buenas tardes")
    return tr("Buenas noches")


def cargar_preferencias() -> dict[str, str]:
    """Recupera preferencias locales sin incluir credenciales."""

    try:
        datos = json.loads(PREFERENCIAS_FILE.read_text(encoding="utf-8"))
        return {
            "nombre": str(datos.get("nombre", "")).strip()[:40] or "Usuario",
            "idioma": str(datos.get("idioma", DEFAULT_LANGUAGE))
            if datos.get("idioma") in LANGUAGE_LABELS
            else DEFAULT_LANGUAGE,
        }
    except (OSError, ValueError, TypeError):
        return {"nombre": "Usuario", "idioma": DEFAULT_LANGUAGE}


def cargar_nombre_usuario() -> str:
    """Recupera el nombre guardado localmente entre ejecuciones."""

    try:
        return cargar_preferencias()["nombre"]
    except (OSError, ValueError, TypeError):
        return "Usuario"


def guardar_preferencias() -> None:
    """Guarda nombre e idioma, nunca datos de autenticación."""

    nombre = str(st.session_state.get("nombre_usuario", "")).strip()[:40] or "Usuario"
    try:
        PREFERENCIAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCIAS_FILE.write_text(
            json.dumps(
                {"nombre": nombre, "idioma": idioma_actual()}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
    except OSError:
        st.session_state["error_preferencias"] = "No fue posible guardar el nombre localmente."


guardar_nombre_usuario = guardar_preferencias


@st.cache_resource(show_spinner=False)
def crear_servicio_ia(
    groq_api_key: str, gemini_api_key: str | None, nombre_usuario: str, idioma: str
) -> AIService:
    """Reutiliza los proveedores durante la sesión sin persistir claves."""

    return AIService(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        nombre_usuario=nombre_usuario,
        idioma=idioma,
    )


def obtener_servicio_ia(nombre_usuario: str) -> AIService | None:
    """Crea los proveedores desde secretos sin mostrar las API Keys."""

    try:
        groq_api_key = str(st.secrets["GROQ_API_KEY"])
    except (KeyError, FileNotFoundError):
        return None
    gemini_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip() or None
    return crear_servicio_ia(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        nombre_usuario=nombre_usuario,
        idioma=idioma_actual(),
    )


def obtener_repositorio_documentos() -> AcademicDocumentRepository:
    """Inicializa el repositorio local protegido de documentos académicos."""

    repositorio = AcademicDocumentRepository(
        database_path=DOCUMENTOS_DB_FILE,
        storage_dir=DOCUMENTOS_DIR,
    )
    repositorio.initialize()
    return repositorio


def recopilar_contexto_personal(fuentes: list[str]) -> dict[str, object]:
    """Recupera solo campos limitados de las fuentes autorizadas por el usuario."""

    contexto: dict[str, object] = {}
    if "Tareas" in fuentes:
        database = TaskDatabase(TAREAS_DB_FILE)
        database.initialize()
        tareas = database.list_tasks()[:10]
        contexto["tareas"] = [
            {
                "titulo": tarea["titulo"],
                "descripcion": tarea["descripcion"],
                "vencimiento": tarea["fecha_vencimiento"],
                "prioridad": tarea["prioridad"],
                "categoria": tarea["categoria"],
                "estado": tarea["estado"],
            }
            for tarea in tareas
        ]

    if "Documentos académicos" in fuentes:
        repositorio = obtener_repositorio_documentos()
        documentos = repositorio.list(limit=5)
        contexto["documentos_academicos"] = [
            {
                "archivo": documento["original_name"],
                "asignatura": documento["subject"],
                "actividad": documento["activity"],
                "estado_evaluacion": documento["evaluation_status"],
                "calificacion": documento["grade"],
                # Solo se comparte un extracto limitado, nunca el archivo binario.
                "contenido_extraido": documento["extracted_text"][:3000],
            }
            for documento in documentos
        ]

    if "Gmail" in fuentes or "Calendario" in fuentes:
        google = obtener_servicio_google()
        if not google or not google.conectado:
            raise GoogleServiceError(
                "Conecta tu cuenta de Google antes de compartir Gmail o Calendar con la IA."
            )
        if "Gmail" in fuentes:
            contexto["correos_recientes"] = [
                {
                    "asunto": correo.get("subject"),
                    "remitente": correo.get("from"),
                    "fecha": correo.get("received"),
                    "no_leido": correo.get("unread"),
                }
                for correo in google.correos(limite=5)
            ]
        if "Calendario" in fuentes:
            contexto["proximos_eventos"] = [
                {
                    "titulo": evento.get("summary"),
                    "inicio": evento.get("start", {}).get("dateTime")
                    or evento.get("start", {}).get("date"),
                    "fin": evento.get("end", {}).get("dateTime")
                    or evento.get("end", {}).get("date"),
                    "ubicacion": evento.get("location"),
                }
                for evento in google.proximos_eventos(limite=5)
            ]
    return contexto


def enviar_consulta_ia(
    servicio: AIService,
    mensaje: str,
    fuentes: list[str] | None = None,
) -> None:
    """Envía una consulta y conserva únicamente el diálogo en la sesión actual."""

    historial = st.session_state.setdefault("chat_messages", [])
    try:
        with st.spinner(tr("MOONA está pensando…")):
            respuesta = generar_respuesta_ia(
                servicio, historial, mensaje, fuentes or [], modo_voz=False
            )
        historial.extend(
            [
                {"role": "user", "content": mensaje},
                {"role": "assistant", "content": respuesta},
            ]
        )
        st.rerun()
    except (AIServiceError, DatabaseError, GoogleServiceError, AcademicDocumentError) as exc:
        st.error(str(exc))


def generar_respuesta_ia(
    servicio: AIService,
    historial: list[dict[str, str]],
    mensaje: str,
    fuentes: list[str],
    *,
    modo_voz: bool,
) -> str:
    """Comparte la recuperación autorizada y el enrutamiento de IA entre modos."""

    contexto = recopilar_contexto_personal(fuentes) if fuentes else None
    return servicio.responder(
        historial,
        mensaje,
        contexto,
        modo_voz=modo_voz,
    )


def _selector_contexto(key: str, *, disabled: bool = False) -> list[str]:
    """Selecciona fuentes personales manteniendo los límites de privacidad."""

    with st.expander(tr("Contexto personal opcional"), expanded=False):
        st.caption(
            tr("Se limitará a 10 tareas, 5 correos sin cuerpo, 5 eventos sin asistentes ni enlaces y 5 documentos con 3.000 caracteres por archivo.")
        )
        return list(
            st.multiselect(
                tr("Fuentes autorizadas"),
                ("Tareas", "Gmail", "Calendario", "Documentos académicos"),
                format_func=tr,
                key=key,
                disabled=disabled,
            )
        )


def _vista_chat(servicio: AIService | None) -> None:
    """Interfaz exclusivamente escrita, sin controles de audio."""

    cabecera, limpiar = st.columns([4, 1])
    cabecera.caption(tr("Conversación escrita · Groq principal · Gemini alternativo"))
    if limpiar.button(tr("Limpiar chat"), use_container_width=True):
        st.session_state["chat_messages"] = []
        st.session_state.pop("consulta_pendiente", None)
        st.rerun()

    historial = st.session_state.setdefault("chat_messages", [])
    if not historial:
        st.markdown(
            f"""<div class="empty-state"><div class="empty-symbol">✦</div>
            <h3>{tr("¿En qué puedo ayudarte?")}</h3>
            <p>{tr("Escribe una consulta general, académica o profesional.")}</p></div>""",
            unsafe_allow_html=True,
        )
    for entrada in historial:
        with st.chat_message(
            entrada["role"],
            avatar=str(MOONA_ICON_PATH) if entrada["role"] == "assistant" else None,
        ):
            st.markdown(entrada["content"])

    fuentes = _selector_contexto("fuentes_chat")
    pendiente = st.session_state.get("consulta_pendiente")
    if pendiente:
        fuentes_pendientes = pendiente["fuentes"]
        st.warning(
            tr("Se enviarán al proveedor de IA datos limitados de ")
            + ", ".join(tr(fuente) for fuente in fuentes_pendientes)
            + tr(". No se enviarán credenciales, cuerpos de correo, enlaces ni asistentes.")
        )
        confirmar, cancelar = st.columns(2)
        if confirmar.button(tr("Confirmar y enviar"), type="primary", use_container_width=True):
            st.session_state.pop("consulta_pendiente", None)
            if servicio is not None:
                enviar_consulta_ia(servicio, pendiente["mensaje"], fuentes_pendientes)
        if cancelar.button(tr("Cancelar"), use_container_width=True):
            st.session_state.pop("consulta_pendiente", None)
            st.rerun()

    mensaje = st.chat_input(
        tr("Escribe tu consulta para MOONA…"),
        disabled=bool(pendiente) or servicio is None,
    )
    if mensaje:
        if fuentes:
            st.session_state["consulta_pendiente"] = {
                "mensaje": mensaje,
                "fuentes": fuentes,
            }
            st.rerun()
        elif servicio is not None:
            enviar_consulta_ia(servicio, mensaje)


def _orb_voz(estado: str) -> str:
    """Construye el indicador visual del estado de la conversación."""

    etiquetas = {
        "idle": ("listening", tr("Conversación detenida"), "○"),
        "listening": ("listening", tr("Escuchando"), "◉"),
        "processing": ("processing", tr("Procesando"), "✦"),
        "responding": ("responding", tr("Respondiendo"), "◉"),
    }
    clase, etiqueta, simbolo = etiquetas.get(estado, etiquetas["idle"])
    return (
        '<div class="voice-console"><div><div class="voice-orb '
        f'{clase}"><span>{simbolo}</span></div><div class="voice-label">'
        f"{etiqueta}</div></div></div>"
    )


def _procesar_voz(
    servicio: AIService,
    audio_bytes: bytes,
    fuentes: list[str],
    indicador: object,
) -> None:
    """Transcribe, consulta la IA y sintetiza la respuesta sin persistir audio."""

    historial = st.session_state.setdefault("voice_messages", [])
    try:
        inicio_total = perf_counter()
        indicador.markdown(_orb_voz("processing"), unsafe_allow_html=True)
        texto = transcribe_wav(
            audio_bytes, language="en-US" if idioma_actual() == "en" else "es-CL"
        )
        fin_transcripcion = perf_counter()
        respuesta = generar_respuesta_ia(
            servicio, historial, texto, fuentes, modo_voz=True
        )
        fin_ia = perf_counter()
        historial.extend(
            [
                {"role": "user", "content": texto},
                {"role": "assistant", "content": respuesta},
            ]
        )
        indicador.markdown(_orb_voz("responding"), unsafe_allow_html=True)
        audio_respuesta: bytes | None = None
        aviso_tts: str | None = None
        try:
            voz = ENGLISH_VOICE if idioma_actual() == "en" else DEFAULT_VOICE
            audio_respuesta = synthesize_speech(respuesta, voz, "+0%")
        except TTSServiceError as exc:
            aviso_tts = str(exc)
        fin_tts = perf_counter()
        st.session_state["voice_response"] = {
            "id": uuid4().hex,
            "text": respuesta,
            "audio": audio_respuesta,
            "rate": 1.0,
            "notice": aviso_tts,
            "timings": {
                "transcription": fin_transcripcion - inicio_total,
                "ai": fin_ia - fin_transcripcion,
                "tts": fin_tts - fin_ia,
                "server_total": fin_tts - inicio_total,
            },
        }
        st.session_state["voice_playback_pending"] = True
        st.session_state["voice_input_generation"] = (
            st.session_state.get("voice_input_generation", 0) + 1
        )
        st.rerun()
    except (
        VoiceServiceError,
        AIServiceError,
        DatabaseError,
        GoogleServiceError,
        AcademicDocumentError,
    ) as exc:
        indicador.markdown(_orb_voz("listening"), unsafe_allow_html=True)
        st.error(str(exc))


def _vista_voz(servicio: AIService | None) -> None:
    """Conversación por voz con transcripción interna y respuesta automática."""

    activo = bool(st.session_state.get("voice_session_active", False))
    respuesta = st.session_state.get("voice_response")
    reproduciendo = bool(st.session_state.get("voice_playback_pending", False))
    indicador = st.empty()
    indicador.markdown(
        _orb_voz("responding" if reproduciendo else "listening" if activo else "idle"),
        unsafe_allow_html=True,
    )
    st.caption(
        tr("El audio se procesa solo en memoria. Detén la grabación para enviar automáticamente tu intervención.")
    )

    fuentes_seleccionadas = _selector_contexto("fuentes_voz", disabled=activo)
    firma_fuentes = tuple(fuentes_seleccionadas)
    if st.session_state.get("voice_sources_signature") != firma_fuentes:
        st.session_state["voice_sources_signature"] = firma_fuentes
        if not activo:
            st.session_state["autorizar_contexto_voz"] = False
    fuentes = (
        list(st.session_state.get("voice_authorized_sources", []))
        if activo
        else fuentes_seleccionadas
    )
    autoriza_audio = st.checkbox(
        tr("Autorizo procesar mis grabaciones mediante el servicio externo de reconocimiento."),
        key="autorizar_sesion_voz",
        disabled=activo,
    )
    autoriza_contexto = True
    if fuentes_seleccionadas:
        autoriza_contexto = st.checkbox(
            tr("Autorizo compartir con la IA los datos limitados de las fuentes seleccionadas durante esta sesión."),
            key="autorizar_contexto_voz",
            disabled=activo,
        )
    if not activo:
        if st.button(
            tr("Iniciar conversación de voz"),
            type="primary",
            use_container_width=True,
            disabled=not autoriza_audio or not autoriza_contexto or servicio is None,
        ):
            st.session_state["voice_session_active"] = True
            st.session_state["voice_authorized_sources"] = list(fuentes_seleccionadas)
            st.session_state.pop("voice_processed_audio", None)
            st.session_state.pop("voice_response", None)
            st.session_state["voice_playback_pending"] = False
            st.rerun()
        return

    if st.button(tr("Detener conversación"), use_container_width=True):
        st.session_state["voice_session_active"] = False
        st.session_state.pop("voice_authorized_sources", None)
        st.session_state["voice_playback_pending"] = False
        st.session_state.pop("voice_response", None)
        st.session_state["voice_input_generation"] = (
            st.session_state.get("voice_input_generation", 0) + 1
        )
        st.rerun()

    if respuesta:
        if respuesta.get("notice"):
            st.caption(respuesta["notice"])
        render_auto_voice_response(
            respuesta["text"],
            respuesta.get("audio"),
            respuesta.get("rate", 1.0),
            playback_id=str(respuesta.get("id", "")),
            timings=respuesta.get("timings"),
            idioma=idioma_actual(),
        )
        if reproduciendo:
            # El navegador confirma el fin real; Python solo libera el estado del rerun.
            st.session_state["voice_playback_pending"] = False

    audio = st.audio_input(
        tr("Micrófono · pulsa para hablar y vuelve a pulsar para finalizar"),
        sample_rate=16_000,
        key=f"audio_voz_{st.session_state.get('voice_input_generation', 0)}",
    )
    if audio is not None and servicio is not None:
        audio_bytes = audio.getvalue()
        huella = hashlib.sha256(audio_bytes).hexdigest()
        if huella != st.session_state.get("voice_processed_audio"):
            # Registrar antes de cualquier llamada evita duplicados en reruns.
            st.session_state["voice_processed_audio"] = huella
            _procesar_voz(servicio, audio_bytes, fuentes, indicador)

    historial = st.session_state.setdefault("voice_messages", [])
    if historial:
        with st.expander(tr("Historial de la conversación de voz"), expanded=False):
            for entrada in historial:
                with st.chat_message(
                    entrada["role"],
                    avatar=str(MOONA_ICON_PATH)
                    if entrada["role"] == "assistant"
                    else None,
                ):
                    st.markdown(entrada["content"])


def vista_asistente() -> None:
    """Presenta modos independientes para chat escrito y conversación por voz."""

    st.markdown(
        f'<h1 class="assistant-title">{tr("Asistente personal")}</h1>',
        unsafe_allow_html=True,
    )
    nombre = str(st.session_state.get("nombre_usuario") or cargar_nombre_usuario())
    servicio = obtener_servicio_ia(nombre)
    if servicio is None:
        st.warning(tr("Configura una API Key de IA en `.streamlit/secrets.toml` para conversar."))
    modo = st.segmented_control(
        tr("Modo de interacción"),
        options=("Chat", "Asistente de voz"),
        format_func=tr,
        default=None if "modo_asistente" in st.session_state else "Chat",
        selection_mode="single",
        key="modo_asistente",
    )
    if modo == "Asistente de voz":
        _vista_voz(servicio)
    else:
        _vista_chat(servicio)


def obtener_servicio_google() -> GoogleWorkspaceService | None:
    """Construye Google desde rutas locales protegidas y conocidas."""

    config = GoogleConfig(
        credentials_file=Path(".streamlit/credentials.json"),
        token_file=Path(".streamlit/token.json"),
        pending_file=Path(".streamlit/oauth_pending.json"),
        redirect_uri="http://localhost:8501",
    )
    if not config.credentials_file.is_file():
        return None
    return GoogleWorkspaceService(GoogleOAuthManager(config))


def bloque_conexion(servicio: GoogleWorkspaceService | None) -> None:
    """Muestra una conexión real o las instrucciones mínimas de configuración."""

    if servicio is None:
        st.warning(
            tr("No se encontró `.streamlit/credentials.json`. Coloca allí el JSON del cliente OAuth web.")
        )
        return
    if servicio.conectado:
        try:
            perfil = servicio.perfil()
            correo = escape(str(perfil.get("emailAddress") or tr("Cuenta de Google")))
            st.markdown(
                f'<div class="account-box"><strong>{tr("Google conectado")}</strong><br><span class="data-meta">{correo}</span></div>',
                unsafe_allow_html=True,
            )
        except GoogleServiceError as exc:
            st.error(str(exc))
        if st.button(tr("Desconectar cuenta"), type="secondary"):
            try:
                servicio.desconectar()
            except GoogleServiceError as exc:
                st.error(str(exc))
                return
            st.rerun()
        return

    try:
        auth_uri = servicio.iniciar_autenticacion()
        st.link_button(tr("Conectar mi cuenta de Google"), auth_uri, type="primary")
    except GoogleServiceError as exc:
        st.error(f"{tr('No se pudo preparar el acceso')}: {tr(str(exc))}")
    st.caption(tr("Solo se solicitará gmail.readonly y calendar.readonly."))


def formatear_fecha(valor: str) -> str:
    """Convierte una fecha ISO a un texto breve y legible."""

    if not valor:
        return tr("Fecha no disponible")
    if len(valor) == 10:
        try:
            fecha = datetime.fromisoformat(valor)
            return (
                fecha.strftime("%m/%d/%Y") + " · " + tr("todo el día")
                if idioma_actual() == "en"
                else fecha.strftime("%d/%m/%Y") + " · " + tr("todo el día")
            )
        except ValueError:
            return valor
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return fecha.strftime("%m/%d/%Y · %I:%M %p" if idioma_actual() == "en" else "%d/%m/%Y · %H:%M")
    except ValueError:
        return valor


def vista_correo() -> None:
    """Busca y presenta mensajes reales de Gmail."""

    st.markdown(f"## {tr('Correo Gmail')}")
    servicio = obtener_servicio_google()
    bloque_conexion(servicio)
    if not servicio or not servicio.conectado:
        return
    busqueda = st.text_input(
        tr("Buscar en Gmail"),
        placeholder="Ej.: from:profesor@universidad.edu after:2026/01/01",
        help=tr("Admite los mismos operadores de búsqueda que Gmail."),
    )
    try:
        with st.spinner(tr("Consultando Gmail…")):
            mensajes = servicio.correos(busqueda=busqueda)
        if not mensajes:
            st.info(tr("No se encontraron mensajes con ese criterio."))
            return
        for mensaje in mensajes:
            autor = mensaje.get("from") or tr("Remitente desconocido")
            asunto = mensaje.get("subject") or tr("Sin asunto")
            estado = f"<span class='unread'>{tr('NUEVO')}</span> · " if mensaje.get("unread") else ""
            st.markdown(
                f"<div class='data-card'><h3>{escape(str(asunto))}</h3>"
                f"<div class='data-meta'>{estado}{escape(str(autor))} · "
                f"{escape(formatear_fecha(str(mensaje.get('received', ''))))}</div></div>",
                unsafe_allow_html=True,
            )
    except GoogleServiceError as exc:
        st.error(str(exc))


def vista_calendario() -> None:
    """Consulta y presenta próximos eventos reales de Google Calendar."""

    st.markdown(f"## {tr('Calendario')}")
    servicio = obtener_servicio_google()
    bloque_conexion(servicio)
    if not servicio or not servicio.conectado:
        return
    try:
        with st.spinner(tr("Consultando el calendario…")):
            eventos = servicio.proximos_eventos()
        if not eventos:
            st.info(tr("No hay eventos en los próximos 30 días."))
            return
        for evento in eventos:
            inicio_evento = evento.get("start", {})
            ubicacion = evento.get("location") or tr("Sin ubicación")
            asunto = evento.get("summary") or tr("Evento sin título")
            inicio = inicio_evento.get("dateTime") or inicio_evento.get("date") or ""
            st.markdown(
                f"<div class='data-card'><h3>{escape(str(asunto))}</h3>"
                f"<div class='data-meta'>{escape(formatear_fecha(str(inicio)))}"
                f" · {escape(str(ubicacion))}</div></div>",
                unsafe_allow_html=True,
            )
    except GoogleServiceError as exc:
        st.error(str(exc))


def vista_documentos() -> None:
    """Carga, consulta, descarga y elimina documentos académicos locales."""

    st.markdown(f"## {tr('Documentos académicos')}")
    st.caption(
        tr("Archivos Word y Excel almacenados solo en este equipo. Su contenido se comparte con la IA únicamente con autorización explícita.")
    )
    try:
        repositorio = obtener_repositorio_documentos()
    except AcademicDocumentError as exc:
        st.error(str(exc))
        return

    with st.expander(tr("Registrar documento"), expanded=False):
        with st.form("form_documento_academico", clear_on_submit=True):
            archivo = st.file_uploader(
                tr("Archivo Word o Excel"),
                type=("docx", "xlsx"),
                accept_multiple_files=False,
            )
            asignatura = st.text_input(tr("Asignatura"), max_chars=120)
            actividad = st.text_input(tr("Actividad"), max_chars=160)
            estado = st.selectbox(tr("Estado de evaluación"), ESTADOS_EVALUACION, format_func=tr)
            calificacion = st.text_input(tr("Calificación opcional"), max_chars=30)
            guardar = st.form_submit_button(
                tr("Guardar documento"), type="primary", use_container_width=True
            )
        if guardar:
            if archivo is None:
                st.error(tr("Selecciona un archivo .docx o .xlsx."))
            else:
                try:
                    repositorio.add(
                        original_name=archivo.name,
                        file_bytes=archivo.getvalue(),
                        subject=asignatura,
                        activity=actividad,
                        evaluation_status=estado,
                        grade=calificacion,
                    )
                    st.session_state["documento_mensaje"] = tr("Documento guardado localmente.")
                    st.rerun()
                except AcademicDocumentError as exc:
                    st.error(str(exc))

    if mensaje := st.session_state.pop("documento_mensaje", None):
        st.success(mensaje)

    try:
        documentos = repositorio.list()
    except AcademicDocumentError as exc:
        st.error(str(exc))
        return
    if not documentos:
        st.markdown(
            f"""<div class="empty-state"><div class="empty-symbol">▤</div>
            <h3>{tr('No hay documentos registrados')}</h3>
            <p>{tr('Carga un archivo Word o Excel para comenzar.')}</p></div>""",
            unsafe_allow_html=True,
        )
        return

    for documento in documentos:
        calificacion_texto = documento["grade"] or tr("Sin calificación")
        st.markdown(
            f"<div class='data-card'><h3>{escape(str(documento['original_name']))}</h3>"
            f"<div class='data-meta'>{escape(str(documento['subject']))} · "
            f"{escape(str(documento['activity']))} · "
            f"{escape(tr(str(documento['evaluation_status'])))} · "
            f"{escape(str(calificacion_texto))}</div></div>",
            unsafe_allow_html=True,
        )
        with st.expander(
            f"{tr('Consultar contenido')} · {documento['original_name']}", expanded=False
        ):
            st.text_area(
                tr("Contenido extraído"),
                value=documento["extracted_text"],
                height=180,
                disabled=True,
                key=f"contenido_documento_{documento['id']}",
            )
        descargar, eliminar = st.columns(2)
        try:
            datos_archivo = repositorio.read_file(documento["id"])
            mime = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if documento["extension"] == ".docx"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            descargar.download_button(
                tr("Descargar"),
                data=datos_archivo,
                file_name=documento["original_name"],
                mime=mime,
                key=f"descargar_documento_{documento['id']}",
                use_container_width=True,
            )
        except AcademicDocumentError as exc:
            descargar.error(str(exc))
        if eliminar.button(
            tr("Eliminar"),
            key=f"eliminar_documento_{documento['id']}",
            use_container_width=True,
        ):
            st.session_state["confirmar_eliminar_documento"] = documento["id"]
            st.rerun()
        if st.session_state.get("confirmar_eliminar_documento") == documento["id"]:
            st.warning(tr("¿Eliminar definitivamente “{nombre}”?", nombre=documento['original_name']))
            confirmar, cancelar = st.columns(2)
            if confirmar.button(
                tr("Sí, eliminar"),
                key=f"confirmar_documento_{documento['id']}",
                type="primary",
                use_container_width=True,
            ):
                try:
                    repositorio.delete(documento["id"])
                    st.session_state.pop("confirmar_eliminar_documento", None)
                    st.session_state["documento_mensaje"] = tr("Documento eliminado.")
                    st.rerun()
                except AcademicDocumentError as exc:
                    st.error(str(exc))
            if cancelar.button(
                tr("Cancelar"),
                key=f"cancelar_documento_{documento['id']}",
                use_container_width=True,
            ):
                st.session_state.pop("confirmar_eliminar_documento", None)
                st.rerun()


def vista_actividades() -> None:
    """Gestiona tareas persistentes con filtros y operaciones CRUD."""

    st.markdown(f"## {tr('Tareas y actividades')}")
    database = TaskDatabase(TAREAS_DB_FILE)
    try:
        database.initialize()
    except DatabaseError as exc:
        st.error(f"{tr('No fue posible iniciar la base de tareas')}: {exc}")
        return

    if mensaje := st.session_state.pop("tarea_mensaje", None):
        st.success(mensaje)

    try:
        conteos = database.count_by_status()
    except DatabaseError as exc:
        st.error(str(exc))
        return

    columnas_metricas = st.columns(3)
    for columna, estado in zip(columnas_metricas, ESTADOS):
        columna.metric(tr(estado), conteos.get(estado, 0))

    with st.expander(tr("＋ Nueva tarea"), expanded=False):
        with st.form("crear_tarea", clear_on_submit=True):
            titulo = st.text_input(tr("Título *"), max_chars=160)
            descripcion = st.text_area(tr("Descripción (opcional)"), max_chars=2000)
            col_fecha, col_prioridad = st.columns(2)
            fecha_vencimiento = col_fecha.date_input(tr("Fecha de vencimiento"), value=date.today())
            prioridad = col_prioridad.selectbox(tr("Prioridad"), PRIORIDADES, index=1, format_func=tr)
            col_categoria, col_estado = st.columns(2)
            categoria = col_categoria.selectbox(tr("Categoría"), CATEGORIAS, format_func=tr)
            estado = col_estado.selectbox(tr("Estado"), ESTADOS, format_func=tr)
            crear = st.form_submit_button(tr("Crear tarea"), type="primary")
        if crear:
            try:
                database.create_task(
                    titulo=titulo,
                    descripcion=descripcion,
                    fecha_vencimiento=fecha_vencimiento,
                    prioridad=prioridad,
                    categoria=categoria,
                    estado=estado,
                )
                st.session_state["tarea_mensaje"] = tr("Tarea creada correctamente.")
                st.rerun()
            except DatabaseError as exc:
                st.error(str(exc))

    tarea_editar_id = st.session_state.get("tarea_editar_id")
    if tarea_editar_id:
        tarea_editar = database.get_task(int(tarea_editar_id))
        if tarea_editar:
            st.markdown(f"### {tr('Editar tarea')}")
            with st.form(f"editar_tarea_{tarea_editar_id}"):
                titulo_editar = st.text_input(
                    tr("Título *"), value=tarea_editar["titulo"], max_chars=160
                )
                descripcion_editar = st.text_area(
                    tr("Descripción (opcional)"), value=tarea_editar["descripcion"] or "", max_chars=2000
                )
                col_fecha, col_prioridad = st.columns(2)
                fecha_editar = col_fecha.date_input(
                    tr("Fecha de vencimiento"), value=date.fromisoformat(tarea_editar["fecha_vencimiento"])
                )
                prioridad_editar = col_prioridad.selectbox(
                    tr("Prioridad"), PRIORIDADES, index=PRIORIDADES.index(tarea_editar["prioridad"]), format_func=tr
                )
                col_categoria, col_estado = st.columns(2)
                categoria_editar = col_categoria.selectbox(
                    tr("Categoría"), CATEGORIAS, index=CATEGORIAS.index(tarea_editar["categoria"]), format_func=tr
                )
                estado_editar = col_estado.selectbox(
                    tr("Estado"), ESTADOS, index=ESTADOS.index(tarea_editar["estado"]), format_func=tr
                )
                guardar = st.form_submit_button(tr("Guardar cambios"), type="primary")
            if guardar:
                try:
                    database.update_task(
                        int(tarea_editar_id),
                        titulo=titulo_editar,
                        descripcion=descripcion_editar,
                        fecha_vencimiento=fecha_editar,
                        prioridad=prioridad_editar,
                        categoria=categoria_editar,
                        estado=estado_editar,
                    )
                    st.session_state.pop("tarea_editar_id", None)
                    st.session_state["tarea_mensaje"] = tr("Tarea actualizada correctamente.")
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))
            if st.button(tr("Cancelar edición"), key="cancelar_edicion"):
                st.session_state.pop("tarea_editar_id", None)
                st.rerun()

    st.markdown(f"### {tr('Tus tareas')}")
    filtros = st.columns(3)
    filtro_categoria = filtros[0].selectbox(tr("Categoría"), ("Todas", *CATEGORIAS), key="filtro_categoria", format_func=tr)
    filtro_prioridad = filtros[1].selectbox(tr("Prioridad"), ("Todas", *PRIORIDADES), key="filtro_prioridad", format_func=tr)
    filtro_estado = filtros[2].selectbox(tr("Estado"), ("Todos", *ESTADOS), key="filtro_estado", format_func=tr)

    try:
        tareas = database.list_tasks(
            categoria=None if filtro_categoria == "Todas" else filtro_categoria,
            prioridad=None if filtro_prioridad == "Todas" else filtro_prioridad,
            estado=None if filtro_estado == "Todos" else filtro_estado,
        )
    except DatabaseError as exc:
        st.error(str(exc))
        return

    if not tareas:
        st.markdown(
            f"""<div class="empty-state"><div class="empty-symbol">✓</div>
            <h3>{tr('No hay tareas para mostrar')}</h3>
            <p>{tr('Crea una tarea o ajusta los filtros para ver otros resultados.')}</p></div>""",
            unsafe_allow_html=True,
        )
        return

    hoy = date.today()
    for tarea in tareas:
        vencida = (
            date.fromisoformat(tarea["fecha_vencimiento"]) < hoy
            and tarea["estado"] != "Completada"
        )
        descripcion_html = ""
        if tarea["descripcion"]:
            descripcion_html = (
                f'<div class="task-description">{escape(tarea["descripcion"]).replace(chr(10), "<br>")}</div>'
            )
        alerta = f'<div class="task-overdue">{tr("VENCIDA")}</div>' if vencida else ""
        clase = "task-card overdue" if vencida else "task-card"

        with st.container(border=False):
            st.markdown(
                f'<div class="{clase}">{alerta}<div class="task-title">{escape(tarea["titulo"])}</div>'
                f'{descripcion_html}<span class="task-badge">{escape(tr(tarea["categoria"]))}</span>'
                f'<span class="task-badge">{tr("Prioridad")} {escape(tr(tarea["prioridad"]))}</span>'
                f'<span class="task-badge">{escape(tr(tarea["estado"]))}</span>'
                f'<span class="task-badge">{tr("Vence")} {escape(tarea["fecha_vencimiento"])}</span></div>',
                unsafe_allow_html=True,
            )
            acciones = st.columns(3)
            if acciones[0].button(tr("Editar"), key=f"editar_{tarea['id']}", use_container_width=True):
                st.session_state["tarea_editar_id"] = tarea["id"]
                st.rerun()
            if acciones[1].button(
                tr("Completar"),
                key=f"completar_{tarea['id']}",
                disabled=tarea["estado"] == "Completada",
                use_container_width=True,
            ):
                try:
                    database.update_task(tarea["id"], estado="Completada")
                    st.session_state["tarea_mensaje"] = tr("Tarea completada.")
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))
            if acciones[2].button(tr("Eliminar"), key=f"eliminar_{tarea['id']}", use_container_width=True):
                st.session_state["confirmar_eliminar_id"] = tarea["id"]
                st.rerun()

            if st.session_state.get("confirmar_eliminar_id") == tarea["id"]:
                st.warning(tr("¿Eliminar definitivamente “{nombre}”?", nombre=tarea['titulo']))
                confirmar, cancelar = st.columns(2)
                if confirmar.button(
                    tr("Sí, eliminar"), key=f"confirmar_{tarea['id']}", type="primary", use_container_width=True
                ):
                    try:
                        database.delete_task(tarea["id"])
                        st.session_state.pop("confirmar_eliminar_id", None)
                        st.session_state["tarea_mensaje"] = tr("Tarea eliminada.")
                        st.rerun()
                    except DatabaseError as exc:
                        st.error(str(exc))
                if cancelar.button(
                    tr("Cancelar"), key=f"cancelar_{tarea['id']}", use_container_width=True
                ):
                    st.session_state.pop("confirmar_eliminar_id", None)
                    st.rerun()


VISTAS: dict[str, Callable[[], None]] = {
    "Asistente": vista_asistente,
    "Correo Gmail": vista_correo,
    "Calendario": vista_calendario,
    "Documentos académicos": vista_documentos,
    "Tareas y actividades": vista_actividades,
}


def barra_lateral() -> tuple[str, str]:
    """Construye la navegación y devuelve el nombre y la sección elegida."""

    with st.sidebar:
        st.markdown(
            f"""<div class="brand"><img class="brand-orb" src="{MOONA_ICON_DATA_URI}" alt="MOONA">
            <div class="brand-name">MOONA</div></div>""",
            unsafe_allow_html=True,
        )
        preferencias = cargar_preferencias()
        if "idioma" not in st.session_state:
            st.session_state["idioma"] = preferencias["idioma"]
        if "nombre_usuario" not in st.session_state:
            st.session_state["nombre_usuario"] = preferencias["nombre"]
        st.selectbox(
            tr("Idioma"),
            options=("en", "es"),
            format_func=lambda codigo: LANGUAGE_LABELS[codigo],
            key="idioma",
            on_change=guardar_preferencias,
        )
        st.text_input(
            tr("¿Cómo quieres que te llame?"),
            key="nombre_usuario",
            max_chars=40,
            on_change=guardar_nombre_usuario,
        )
        if error := st.session_state.pop("error_preferencias", None):
            st.warning(tr(error))
        st.caption(tr("NAVEGACIÓN"))
        seleccion = st.radio(
            "Secciones",
            options=[seccion.nombre for seccion in SECCIONES],
            format_func=tr,
            label_visibility="collapsed",
            key="seccion_nav",
        )
        st.markdown(
            f'<div class="sidebar-footer">MOONA LOCAL · {tr("INTERFAZ")} V0.1</div>',
            unsafe_allow_html=True,
        )
    nombre = str(st.session_state["nombre_usuario"]).strip() or "Usuario"
    return nombre, seleccion


def inicio(nombre: str, conectado: bool = False) -> None:
    """Muestra el saludo, la fecha y los indicadores generales."""

    st.markdown(
        f"""<section class="hero"><div class="eyebrow">MOONA · {tr('Sistema de asistencia personal')}</div>
        <h1>{saludo_segun_hora()}, {escape(nombre)}.</h1>
        <p>{fecha_localizada()}</p>
        <div class="status-row"><span class="status-pill"><span class="status-dot"></span>{tr('Interfaz activa')}</span>
        <span class="status-pill">{tr('Google conectado') if conectado else tr('Modo local')}</span></div></section>""",
        unsafe_allow_html=True,
    )


def main() -> None:
    """Coordina la interfaz y procesa el callback OAuth sin exponer parámetros."""

    aplicar_estilos()
    servicio = obtener_servicio_google()

    # Rechaza parámetros repetidos antes de procesar el callback OAuth.
    if any(clave in st.query_params for clave in ("code", "state", "error")):
        try:
            respuesta: dict[str, str] = {}
            for clave in ("code", "state", "error"):
                valores = st.query_params.get_all(clave)
                if len(valores) > 1:
                    raise GoogleServiceError("La respuesta OAuth contiene parámetros repetidos.")
                if valores:
                    respuesta[clave] = valores[0]
            if servicio is None:
                raise GoogleServiceError("No se encontró `.streamlit/credentials.json`.")
            servicio.completar_autenticacion(respuesta)
            st.session_state["oauth_resultado"] = ("success", "Cuenta de Google conectada correctamente.")
        except GoogleServiceError as exc:
            st.session_state["oauth_resultado"] = ("error", str(exc))
        finally:
            # El código OAuth se elimina de la URL inmediatamente y no se registra.
            st.query_params.clear()
            st.rerun()

    resultado_oauth = st.session_state.pop("oauth_resultado", None)
    if resultado_oauth:
        tipo, mensaje = resultado_oauth
        (st.success if tipo == "success" else st.error)(tr(mensaje))

    nombre, seleccion = barra_lateral()
    inicio(nombre, bool(servicio and servicio.conectado))
    VISTAS[seleccion]()


if __name__ == "__main__":
    main()
