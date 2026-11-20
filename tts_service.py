"""Síntesis neuronal de voz para JARVIS mediante Edge TTS.

El audio se genera y conserva únicamente en memoria. Si el servicio remoto no
está disponible, la interfaz puede recurrir a la síntesis del navegador.
"""

from __future__ import annotations

import asyncio
from typing import Final

import edge_tts


DEFAULT_VOICE: Final[str] = "es-CL-CatalinaNeural"
ENGLISH_VOICE: Final[str] = "en-US-AriaNeural"
VOICE_OPTIONS: Final[dict[str, str]] = {
    "Lorenzo · masculino · Chile": "es-CL-LorenzoNeural",
    "Catalina · femenino · Chile": "es-CL-CatalinaNeural",
    "Aria · female · United States": ENGLISH_VOICE,
}
RATE_OPTIONS: Final[dict[str, str]] = {
    "Lenta": "-15%",
    "Normal": "+0%",
    "Rápida": "+15%",
}


class TTSServiceError(Exception):
    """Error seguro y controlado durante la síntesis de voz."""


async def _synthesize(text: str, voice: str, rate: str) -> bytes:
    audio = bytearray()
    communicator = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    async for chunk in communicator.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
) -> bytes:
    """Genera MP3 en memoria usando una voz autorizada de la configuración."""

    english = voice.startswith("en-")
    clean_text = text.strip() if isinstance(text, str) else ""
    if not clean_text:
        raise TTSServiceError("There is no response to play." if english else "No hay una respuesta para reproducir.")
    if voice not in VOICE_OPTIONS.values():
        raise TTSServiceError("The selected voice is not allowed." if english else "La voz seleccionada no está permitida.")
    if rate not in RATE_OPTIONS.values():
        raise TTSServiceError("The selected speed is invalid." if english else "La velocidad seleccionada no es válida.")

    try:
        # Un límite evita que Streamlit quede esperando indefinidamente a Edge.
        audio = asyncio.run(asyncio.wait_for(_synthesize(clean_text, voice, rate), 15))
    except Exception as exc:
        raise TTSServiceError(
            "The neural voice is unavailable; the browser voice will be used."
            if english else "La voz neuronal no está disponible; se usará la voz del navegador."
        ) from exc
    if not audio:
        raise TTSServiceError(
            "The neural voice returned no audio; the browser voice will be used."
            if english else "La voz neuronal no devolvió audio; se usará la voz del navegador."
        )
    return audio
