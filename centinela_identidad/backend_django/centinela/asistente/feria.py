"""Modo feria (ASISTENTE_MODO_FERIA=true): precalienta al arrancar y deja claro el estado en consola."""
import threading
import time

from . import config, red, voz


def activo():
    return config.env("ASISTENTE_MODO_FERIA").lower() in ("1", "true", "si", "sí")


def _precalentar():
    from .proveedores import stream_groq, ProveedorError
    print("[FERIA] Precalentando (Groq + edge-tts)...", flush=True)
    if not red.hay_internet():
        print("[FERIA] *** SIN INTERNET: el asistente seguirá con atajos locales (SOS, navegación) "
              "y respuestas locales. Voz del navegador.", flush=True)
        return
    t = time.perf_counter()
    try:
        "".join(stream_groq("Responde solo: ok", [{"role": "user", "content": "hola"}], max_tokens=3))
        print(f"[FERIA] Groq OK ({(time.perf_counter() - t) * 1000:.0f} ms)", flush=True)
    except ProveedorError as e:
        print(f"[FERIA] *** Groq NO respondió ({e.kind}): {e}. Se usará Gemini/Claude.", flush=True)
    t = time.perf_counter()
    try:
        voz.sintetizar("Listo.")
        print(f"[FERIA] edge-tts OK ({(time.perf_counter() - t) * 1000:.0f} ms)", flush=True)
    except Exception as e:
        print(f"[FERIA] *** edge-tts NO respondió ({type(e).__name__}). Se usará la voz del navegador.", flush=True)


def iniciar():
    """Se llama al arrancar Django. Sin modo feria solo precalienta edge-tts (como antes)."""
    if activo():
        print("[FERIA] MODO FERIA ACTIVO", flush=True)
        threading.Thread(target=_precalentar, daemon=True).start()
    else:
        voz.precalentar()
