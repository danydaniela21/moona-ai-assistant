"""Servicio de transcripción de voz para JARVIS.

El audio se procesa exclusivamente en memoria. Este módulo no guarda
grabaciones ni registra su contenido.
"""

from __future__ import annotations

from io import BytesIO
from typing import Final

import speech_recognition as sr


LANGUAGES: Final[set[str]] = {"es-CL", "en-US"}


class VoiceServiceError(Exception):
    """Error controlado del servicio de voz, seguro para mostrar al usuario."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def transcribe_wav(
    audio_bytes: bytes,
    recognizer: sr.Recognizer | None = None,
    language: str = "es-CL",
) -> str:
    """Transcribe audio WAV en memoria mediante Google Speech Recognition.

    Args:
        audio_bytes: Contenido binario de una grabación WAV.
        recognizer: Reconocedor opcional, inyectable para facilitar las pruebas.

    Returns:
        Texto reconocido, sin espacios al inicio ni al final.

    Raises:
        VoiceServiceError: Si el audio está vacío, es inválido, no se
            comprende o el servicio externo no está disponible.
    """
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise VoiceServiceError(
            "No audio recording was received." if language == "en-US" else "No se recibió una grabación de audio.",
            code="empty_audio",
        )

    speech_recognizer = recognizer or sr.Recognizer()
    # Evita que una conexión intermitente deje el rerun de Streamlit bloqueado.
    if speech_recognizer.operation_timeout is None:
        speech_recognizer.operation_timeout = 12

    try:
        # BytesIO evita crear archivos temporales o persistir la grabación.
        with sr.AudioFile(BytesIO(audio_bytes)) as source:
            audio_data = speech_recognizer.record(source)
    except (EOFError, OSError, ValueError) as exc:
        raise VoiceServiceError(
            "The recording does not contain valid WAV audio." if language == "en-US" else "La grabación no contiene audio WAV válido.",
            code="invalid_audio",
        ) from exc

    if not getattr(audio_data, "frame_data", b""):
        raise VoiceServiceError(
            "The recording is empty or contains no processable sound." if language == "en-US" else "La grabación está vacía o no contiene sonido procesable.",
            code="empty_audio",
        )

    try:
        transcription = speech_recognizer.recognize_google(
            audio_data,
            language=language if language in LANGUAGES else "en-US",
        )
    except sr.UnknownValueError as exc:
        raise VoiceServiceError(
            "The audio could not be understood. Try speaking closer to the microphone." if language == "en-US" else "No fue posible comprender el audio. Intenta hablar más cerca del micrófono.",
            code="unrecognized_audio",
        ) from exc
    except sr.RequestError as exc:
        raise VoiceServiceError(
            "The transcription service could not be reached. Please try again later." if language == "en-US" else "No fue posible contactar el servicio de transcripción. Intenta nuevamente más tarde.",
            code="service_unavailable",
        ) from exc

    text = transcription.strip() if isinstance(transcription, str) else ""
    if not text:
        raise VoiceServiceError(
            "No text could be obtained from the recording." if language == "en-US" else "No fue posible obtener texto de la grabación.",
            code="unrecognized_audio",
        )

    return text
