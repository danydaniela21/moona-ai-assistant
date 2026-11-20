"""Controles locales de síntesis de voz mediante Web Speech API del navegador."""

from __future__ import annotations

import json
import re
import base64

import streamlit.components.v1 as components
import streamlit as st


def _texto_para_voz(texto: str) -> str:
    """Retira marcas comunes de Markdown para una lectura más natural."""

    limpio = re.sub(r"```.*?```", " bloque de código ", texto, flags=re.DOTALL)
    limpio = re.sub(r"`([^`]*)`", r"\1", limpio)
    limpio = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", limpio)
    limpio = re.sub(r"[#*_>~-]+", " ", limpio)
    return re.sub(r"\s+", " ", limpio).strip()


def build_tts_html(texto: str) -> str:
    """Genera HTML seguro con controles de reproducción y detención."""

    # Escapar '<' evita que una respuesta pueda cerrar el bloque script.
    texto_json = json.dumps(_texto_para_voz(texto), ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    return f"""
    <style>
      body {{ margin:0; background:transparent; font-family:Inter,system-ui,sans-serif; }}
      .controls {{ display:flex; gap:8px; align-items:center; }}
      button {{
        color:#FCE7F3; background:rgba(39,13,34,.92); border:1px solid rgba(244,114,182,.34);
        border-radius:999px; padding:6px 12px; cursor:pointer; font-size:12px;
      }}
      button:hover {{ color:#FF69B4; border-color:#FF1493; }}
      #status {{ color:#D8A7C2; font-size:11px; }}
    </style>
    <div class="controls">
      <button id="speak" type="button">🔊 Escuchar</button>
      <button id="stop" type="button">■ Detener</button>
      <span id="status"></span>
    </div>
    <script>
      const text = {texto_json};
      const synth = window.speechSynthesis;
      const status = document.getElementById('status');
      const chunks = text.match(/.{{1,180}}(?:\\s|$)/g) || [text];
      let playbackId = 0;

      function stopPlayback() {{
        playbackId += 1;
        if (synth) synth.cancel();
        status.textContent = '';
      }}

      function speakChunk(index, activeId) {{
        if (!synth || activeId !== playbackId) return;
        if (index >= chunks.length) {{ status.textContent = ''; return; }}
        const utterance = new SpeechSynthesisUtterance(chunks[index]);
        utterance.lang = 'es-CL';
        const voices = synth.getVoices();
        const voice = voices.find(v => v.lang.toLowerCase() === 'es-cl')
          || voices.find(v => v.lang.toLowerCase().startsWith('es'));
        if (voice) utterance.voice = voice;
        utterance.rate = 0.98;
        utterance.onstart = () => {{
          if (activeId === playbackId) status.textContent = 'Reproduciendo';
        }};
        utterance.onend = () => speakChunk(index + 1, activeId);
        utterance.onerror = event => {{
          if (activeId !== playbackId) return;
          if (event.error === 'interrupted' || event.error === 'canceled') return;
          status.textContent = 'No se pudo reproducir';
        }};
        synth.speak(utterance);
      }}

      document.getElementById('speak').onclick = () => {{
        if (!synth || !('SpeechSynthesisUtterance' in window)) {{
          status.textContent = 'No disponible en este navegador'; return;
        }}
        stopPlayback();
        const activeId = playbackId;
        setTimeout(() => speakChunk(0, activeId), 75);
      }};
      document.getElementById('stop').onclick = stopPlayback;
    </script>
    """


def render_tts_controls(texto: str) -> None:
    """Inserta los controles sin enviar el texto a servicios externos."""

    components.html(build_tts_html(texto), height=42, scrolling=False)


def build_auto_tts_html(
    texto: str,
    audio_mp3: bytes | None = None,
    velocidad: float = 1.0,
    playback_id: str = "",
    timings: dict[str, float] | None = None,
    idioma: str = "es",
) -> str:
    """Genera reproducción automática con Edge MP3 y respaldo del navegador."""

    texto_json = json.dumps(_texto_para_voz(texto), ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    audio_src = ""
    if audio_mp3:
        encoded = base64.b64encode(audio_mp3).decode("ascii")
        audio_src = f'data:audio/mpeg;base64,{encoded}'
    audio_json = json.dumps(audio_src)
    playback_json = json.dumps(playback_id or "voice-response")
    lang = "en-US" if idioma == "en" else "es-CL"
    labels = (
        {"responding": "Responding", "stop": "Stop voice", "ready": "Ready to listen", "unavailable": "Playback unavailable", "failed": "Playback failed", "stopped": "Voice stopped", "transcription": "Transcription", "voice": "Voice", "playback": "Playback"}
        if idioma == "en"
        else {"responding": "Respondiendo", "stop": "Detener voz", "ready": "Lista para escuchar", "unavailable": "Reproducción no disponible", "failed": "No se pudo reproducir", "stopped": "Voz detenida", "transcription": "Transcripción", "voice": "Voz", "playback": "Reproducción"}
    )
    medidas = timings or {}
    metricas = (
        f"{labels['transcription']} {medidas.get('transcription', 0):.2f}s · "
        f"IA {medidas.get('ai', 0):.2f}s · "
        f"{labels['voice']} {medidas.get('tts', 0):.2f}s"
        if medidas
        else ""
    )
    metricas_json = json.dumps(metricas, ensure_ascii=False).replace("<", "\\u003c")
    return f"""
    <style>
      #jarvis-auto-voice {{ margin:0; background:transparent; font-family:Inter,system-ui,sans-serif; }}
      #jarvis-auto-voice .voice-status {{ display:flex; justify-content:center; align-items:center; gap:10px;
        color:#FBCFE8; font-size:12px; letter-spacing:.08em; text-transform:uppercase; }}
      #jarvis-auto-voice .dot {{ width:8px; height:8px; border-radius:50%; background:#FF1493;
        box-shadow:0 0 12px #FF69B4; animation:pulse 1.1s ease-in-out infinite; }}
      #jarvis-auto-voice button {{ color:#FCE7F3; background:rgba(39,13,34,.92); border:1px solid rgba(244,114,182,.34);
        border-radius:999px; padding:6px 12px; cursor:pointer; font-size:12px; }}
      #jarvis-auto-voice .metrics {{ margin-top:5px; color:#B982A2; text-align:center; font-size:10px; }}
      @keyframes pulse {{ 50% {{ opacity:.35; transform:scale(.7); }} }}
    </style>
    <div id="jarvis-auto-voice"><div class="voice-status"><span class="dot"></span><span id="state">{labels['responding']}</span>
      <button id="stop" type="button">{labels['stop']}</button></div>
    <div class="metrics" id="metrics"></div>
    <audio id="edgeAudio" src={audio_json} autoplay></audio></div>
    <script>
      const text = {texto_json};
      const playbackId = {playback_json};
      const serverMetrics = {metricas_json};
      const audio = document.getElementById('edgeAudio');
      const state = document.getElementById('state');
      const metrics = document.getElementById('metrics');
      const synth = window.speechSynthesis;
      let utterance = null;
      let playbackStartedAt = 0;
      let playStarted = false;
      let fallbackStarted = false;
      let stopped = false;
      const storageKey = `jarvis-played-${{playbackId}}`;

      metrics.textContent = serverMetrics;

      function globalState(label, className) {{
        const labelNode = document.querySelector('.voice-console .voice-label');
        const orb = document.querySelector('.voice-console .voice-orb');
        if (labelNode) labelNode.textContent = label;
        if (orb) orb.className = `voice-orb ${{className}}`;
      }}

      function finished() {{
        if (stopped) return;
        sessionStorage.setItem(storageKey, 'done');
        const elapsed = playbackStartedAt ? (performance.now() - playbackStartedAt) / 1000 : 0;
        state.textContent = {json.dumps(labels['ready'])};
        globalState({json.dumps(labels['ready'])}, 'listening');
        if (elapsed > 0) metrics.textContent = `${{serverMetrics}} · {labels['playback']} ${{elapsed.toFixed(2)}}s`;
      }}

      function browserFallback() {{
        if (fallbackStarted || stopped || sessionStorage.getItem(storageKey) === 'done') return;
        if (!synth || !('SpeechSynthesisUtterance' in window)) {{
          state.textContent = {json.dumps(labels['unavailable'])}; return;
        }}
        fallbackStarted = true;
        synth.cancel();
        utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = '{lang}';
        utterance.rate = {float(velocidad):.2f};
        const voices = synth.getVoices();
        utterance.voice = voices.find(v => v.lang.toLowerCase() === '{lang.lower()}')
          || voices.find(v => v.lang.toLowerCase().startsWith('{lang[:2].lower()}')) || null;
        utterance.onstart = () => {{
          playbackStartedAt = performance.now();
          globalState({json.dumps(labels['responding'])}, 'responding');
        }};
        utterance.onend = finished;
        utterance.onerror = event => {{
          if (event.error !== 'interrupted' && event.error !== 'canceled')
            state.textContent = {json.dumps(labels['failed'])};
        }};
        synth.speak(utterance);
      }}

      async function attemptPlayback(attempt = 0) {{
        if (stopped || playStarted || sessionStorage.getItem(storageKey) === 'done') return;
        if (!audio.getAttribute('src')) {{ browserFallback(); return; }}
        try {{
          await audio.play();
        }} catch (error) {{
          if (attempt < 4) {{
            window.setTimeout(() => attemptPlayback(attempt + 1), 250 * (attempt + 1));
          }} else {{ browserFallback(); }}
        }}
      }}

      if (sessionStorage.getItem(storageKey) === 'done') {{
        state.textContent = {json.dumps(labels['ready'])};
        globalState({json.dumps(labels['ready'])}, 'listening');
      }} else if (audio.getAttribute('src')) {{
        audio.preload = 'auto';
        audio.onplaying = () => {{
          playStarted = true;
          playbackStartedAt = performance.now();
          state.textContent = {json.dumps(labels['responding'])};
          globalState({json.dumps(labels['responding'])}, 'responding');
        }};
        audio.onended = finished;
        audio.onerror = browserFallback;
        if (audio.readyState >= 2) attemptPlayback();
        else audio.addEventListener('canplay', () => attemptPlayback(), {{ once:true }});
        window.setTimeout(() => attemptPlayback(), 300);
        document.addEventListener('visibilitychange', () => {{
          if (!document.hidden) attemptPlayback();
        }});
      }} else {{ browserFallback(); }}

      document.getElementById('stop').onclick = () => {{
        stopped = true;
        sessionStorage.setItem(storageKey, 'done');
        audio.pause(); audio.currentTime = 0;
        if (synth) synth.cancel();
        state.textContent = {json.dumps(labels['stopped'])};
        globalState({json.dumps(labels['ready'])}, 'listening');
      }};
    </script>
    """


def render_auto_voice_response(
    texto: str,
    audio_mp3: bytes | None = None,
    velocidad: float = 1.0,
    playback_id: str = "",
    timings: dict[str, float] | None = None,
    idioma: str = "es",
) -> None:
    """Reproduce una respuesta y vuelve visualmente al estado de escucha."""

    st.html(
        build_auto_tts_html(texto, audio_mp3, velocidad, playback_id, timings, idioma),
        unsafe_allow_javascript=True,
    )
