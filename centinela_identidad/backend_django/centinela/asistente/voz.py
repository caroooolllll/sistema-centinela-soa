"""Voz: Whisper (Groq) para voz->texto y edge-tts para texto->voz."""
import asyncio
import re

import httpx

from . import config
from .proveedores import ProveedorError, _error_http


def transcribir(audio_bytes, nombre="voz.webm", mime="audio/webm"):
    """Groq Whisper. Lanza ProveedorError si falla (el frontend cae al reconocimiento del navegador)."""
    k = config.key("GROQ_API_KEY")
    if not k:
        raise ProveedorError("auth", "GROQ_API_KEY no configurada")
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {k}"},
            files={"file": (nombre, audio_bytes, mime)},
            data={"model": config.groq_stt_modelo(), "language": "es", "temperature": "0",
                  "response_format": "json",
                  "prompt": "Centinela, privada, reporte, aviso, evento, encuesta, auxilio, emergencia."},
            timeout=httpx.Timeout(20.0, connect=4.0),
        )
    except httpx.HTTPError as e:
        raise ProveedorError("otro", f"red: {type(e).__name__}")
    if r.status_code != 200:
        raise _error_http(r.status_code, r.text, r.headers)
    return (r.json().get("text") or "").strip()


_LIMPIAR_TTS = re.compile(r"[\U0001F000-\U0001FAFF☀-➿•*_#`]")


def limpiar_para_voz(texto):
    return re.sub(r"\s+", " ", _LIMPIAR_TTS.sub(" ", texto or "")).strip()


async def _sintetizar(texto, voz):
    import edge_tts
    partes = []
    async for ch in edge_tts.Communicate(texto, voz).stream():
        if ch["type"] == "audio":
            partes.append(ch["data"])
    return b"".join(partes)


def precalentar():
    """Primera síntesis en segundo plano al arrancar: evita ~2 s extra en la primera respuesta hablada."""
    import threading

    def _calentar():
        try:
            sintetizar("Listo.")
        except Exception:
            pass
    threading.Thread(target=_calentar, daemon=True).start()


def sintetizar(texto, voz=None):
    """mp3 (bytes) de UNA oración con edge-tts. Lanza excepción si falla."""
    texto = limpiar_para_voz(texto)[:600]
    if not texto:
        return b""
    return asyncio.run(asyncio.wait_for(_sintetizar(texto, voz or config.tts_voz()), timeout=12))
