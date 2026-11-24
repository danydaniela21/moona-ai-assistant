"""Tarjetas del Social Hub en la vista del asistente de MOONA."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import quote

import streamlit as st

from i18n import translate
from moona_connect_state import NUMBER_STATES, read_social_indicators


@dataclass(frozen=True)
class Plataforma:
    clave: str
    nombre: str
    url: str
    icono: str
    color: str


PLATAFORMAS = (
    Plataforma(
        "instagram", "Instagram", "https://www.instagram.com/",
        '<defs><linearGradient id="ig" x2="100%" y2="0%" gradientTransform="rotate(-45 .5 .5)">'
        '<stop stop-color="#FCAF45"/><stop offset=".55" stop-color="#E1306C"/>'
        '<stop offset="1" stop-color="#833AB4"/></linearGradient></defs>'
        '<rect width="24" height="24" rx="6" fill="url(#ig)"/>'
        '<rect x="4.5" y="4.5" width="15" height="15" rx="4" fill="none" stroke="#fff" stroke-width="1.7"/>'
        '<circle cx="12" cy="12" r="3.4" fill="none" stroke="#fff" stroke-width="1.7"/>'
        '<circle cx="16.6" cy="7.5" r="1" fill="#fff"/>', "#E1306C",
    ),
    Plataforma(
        "facebook", "Facebook", "https://www.facebook.com/",
        '<circle cx="12" cy="12" r="11.8" fill="#fff"/>'
        '<path d="M24 12.07a12 12 0 1 0-13.88 11.86v-8.39H7.08v-3.47h3.04V9.43c0-3.01 '
        '1.8-4.67 4.54-4.67 1.31 0 2.69.24 2.69.24v2.95h-1.52c-1.49 0-1.95.93-1.95 '
        '1.88v2.24h3.32l-.53 3.47h-2.79v8.39A12 12 0 0 0 24 12.07Z"/>', "#0866FF",
    ),
    Plataforma(
        "whatsapp", "WhatsApp Web", "https://web.whatsapp.com/",
        '<path d="M12 2a9.8 9.8 0 0 0-8.5 14.7L2 22l5.4-1.4A9.8 9.8 0 1 0 12 2Z" '
        'stroke="#25D366" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M7.8 6.6c-.7.2-1.3 1-1.3 2 0 3.7 4.9 8.5 8.5 8.5 1.1 0 2.1-.7 2.3-1.7 '
        '.1-.4 0-.7-.4-.9l-2.3-1.1c-.4-.2-.6-.1-.9.2l-.8 1c-1.7-.8-3.3-2.3-4.1-4l.9-1 '
        'c.2-.2.2-.5.1-.8l-.9-2c-.2-.4-.6-.3-1.1-.2Z" fill="#fff"/>', "#25D366",
    ),
    Plataforma(
        "linkedin", "LinkedIn", "https://www.linkedin.com/",
        '<rect x="2" y="2" width="20" height="20" rx="3"/>'
        '<path fill="#fff" d="M6 9.5h2.6V18H6zm4.4 0h2.5v1.2c.5-.9 1.4-1.4 2.6-1.4 '
        '2.7 0 3 1.8 3 4V18H16v-4.2c0-1 0-2.2-1.4-2.2s-1.6 1.1-1.6 2.1V18h-2.6z"/>'
        '<circle fill="#fff" cx="7.3" cy="6.7" r="1.5"/>', "#0A66C2",
    ),
)


ESTILOS = """
<style>
.moona-social-hub { max-width: 66rem; }
.moona-social-hub h2 {
    color: #FCE7F3;
    font-size: clamp(1.4rem, 2.5vw, 2rem);
    line-height: 1.2;
    padding: 0;
    margin: 0 0 .5rem;
}
.moona-social-hub .social-hub-enlaces {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: clamp(.55rem, 1.3vw, 1rem);
}
.moona-social-hub a {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-rows: auto 1fr;
    align-items: center;
    gap: .24rem;
    min-height: clamp(5.1rem, 7.15vw, 6.25rem);
    min-width: 0;
    padding: clamp(.48rem, .8vw, .72rem);
    border: 1px solid var(--line);
    border-radius: 16px;
    background: linear-gradient(145deg, rgba(47, 22, 43, .79), rgba(13, 7, 20, .65));
    color: #FCE7F3;
    text-decoration: none;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06);
}
.moona-social-hub a:hover {
    border-color: #FF69B4;
    background: linear-gradient(145deg, rgba(72, 24, 56, .87), rgba(20, 9, 27, .76));
    color: #FCE7F3;
    text-decoration: none;
}
.moona-social-hub a:focus-visible { outline: 2px solid #FF95CE; outline-offset: -3px; }
.moona-social-hub .social-hub-marca {
    grid-column: 1 / -1;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    width: 100%;
    min-height: 2.15rem;
    gap: .25rem;
}
.moona-social-hub .social-hub-marca img {
    width: clamp(1.55rem, 2.4vw, 2rem);
    height: auto;
    aspect-ratio: 1;
    flex: none;
}
.moona-social-hub .social-hub-nombre {
    font-size: clamp(.86rem, 1.45vw, 1.15rem);
    font-weight: 650;
    line-height: 1.2;
    overflow-wrap: anywhere;
}
.moona-social-hub .notificaciones {
    color: var(--muted);
    font-size: .74rem;
    line-height: 1.2;
    overflow-wrap: anywhere;
}
.moona-social-hub .social-hub-estado { text-align: end; }
.moona-social-hub .social-hub-estado:empty { display: none; }
.moona-social-hub .social-hub-marca .notificaciones {
    display: grid;
    place-items: center;
    min-width: 1.8rem;
    min-height: 1.8rem;
    padding: .2rem .34rem;
    border-radius: 999px;
    background: #C0146D;
    color: #fff;
    font-size: .77rem;
    font-weight: 750;
    text-align: center;
}
@media (max-width: 768px) {
    .moona-social-hub .social-hub-enlaces { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .moona-social-hub a { grid-template-columns: 1fr; grid-template-rows: auto auto 1fr; }
    .moona-social-hub .social-hub-estado { text-align: start; }
}
@media (min-width: 769px) and (max-height: 760px) {
    .moona-social-hub a { min-height: 5.2rem; }
    .moona-social-hub h2 { font-size: 1.45rem; }
}
</style>
"""



ESTADOS_CONNECT = {
    "unknown": "Desconocido",
    "no_tab": "Sin pestaña",
    "unauthorized": "Sin permiso",
    "unavailable": "No disponible",
    "stale": "Desactualizado",
    "disconnected": "Sin conexión",
}


@st.fragment(run_every=5)
def renderizar_social_hub(idioma: str) -> None:
    """Actualiza el Social Hub sin volver a ejecutar las otras vistas de MOONA."""
    notificaciones = read_social_indicators()
    titulo = escape(translate("Social Hub", idioma))
    nueva_pestana = translate("Se abre en una pestaña nueva", idioma)
    enlaces = []
    for plataforma in PLATAFORMAS:
        nombre = translate(plataforma.nombre, idioma)
        etiqueta = f"{nombre}. {nueva_pestana}"
        icono = quote(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{plataforma.color}">'
            f"{plataforma.icono}</svg>"
        )
        novedad = notificaciones.get(plataforma.clave)
        indicador = ""
        contador = ""
        if novedad is not None:
            if novedad.state in NUMBER_STATES:
                texto = f"{novedad.value}{'+' if novedad.state == 'lower_bound' else ''}"
                detalle = translate("Indicador en el título: {valor}", idioma, valor=texto)
            else:
                texto = detalle = translate(ESTADOS_CONNECT[novedad.state], idioma)
            if novedad.updated_at:
                fecha = translate("Actualizado (UTC): {fecha}", idioma, fecha=novedad.updated_at)
                detalle = f"{detalle}. {fecha}"
            etiqueta += f". {detalle}"
            indicador = (
                f'<span class="notificaciones" aria-hidden="true" data-state="{novedad.state}" '
                f'title="{escape(detalle)}">{escape(texto)}</span>'
            )
            if novedad.state in NUMBER_STATES:
                contador, indicador = indicador, ""

        enlaces.append(
            f'<a href="{plataforma.url}" target="_blank" rel="noopener noreferrer" '
            f'aria-label="{escape(etiqueta)}"><span class="social-hub-marca">'
            f'<img src="data:image/svg+xml,{icono}" alt="">{contador}</span>'
            f'<span class="social-hub-nombre">{escape(nombre)}</span>'
            f'<span class="social-hub-estado">{indicador}</span></a>'
        )

    contenido = "".join(enlaces)
    st.html(
        f'{ESTILOS}\n<nav class="moona-social-hub" aria-labelledby="moona-social-title">'
        f'<h2 id="moona-social-title">{titulo}</h2>'
        f'<div class="social-hub-enlaces">{contenido}</div></nav>',
    )
