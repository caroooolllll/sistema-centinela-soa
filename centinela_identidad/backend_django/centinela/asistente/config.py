"""Configuración del asistente (todo desde .env). Nunca se loguean valores de keys."""
import os

_PLACEHOLDERS = ("", "tu_api_key_aqui", "your_api_key_here", "pega_tu_key_aqui")


def env(nombre, defecto=""):
    return os.getenv(nombre, defecto).strip()


def key(nombre):
    v = env(nombre)
    return v if v not in _PLACEHOLDERS else None


def cadena():
    """Orden de proveedores: ASISTENTE_CADENA=groq,gemini,claude,local"""
    raw = env("ASISTENTE_CADENA", "groq,gemini,claude,local")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def groq_modelo():
    return env("GROQ_MODELO", "llama-3.3-70b-versatile")


def groq_stt_modelo():
    return env("GROQ_STT_MODELO", "whisper-large-v3-turbo")


def gemini_modelo():
    return env("GEMINI_MODELO", "gemini-2.0-flash")


def claude_modelo():
    return env("CLAUDE_MODELO", "claude-sonnet-4-5")


def tts_voz():
    return env("TTS_VOZ", "es-MX-DaliaNeural")


def espera_429_max():
    """Segundos máximos que se espera por un 429 'por minuto' antes de saltar de proveedor."""
    return float(env("ASISTENTE_ESPERA_429_MAX", "4"))


def sdri_url():
    return env("SDRI_URL", "http://127.0.0.1:9001")


_avisado = False


def verificar_keys():
    """Avisa claramente en consola si falta alguna key. Devuelve lista de faltantes."""
    global _avisado
    faltan = [n for n in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY") if not key(n)]
    if _avisado:
        return faltan
    _avisado = True
    para = {
        "GROQ_API_KEY": "voz a texto (Whisper) y cerebro principal",
        "GEMINI_API_KEY": "primer respaldo (Gemini Flash)",
        "ANTHROPIC_API_KEY": "respaldo Claude, análisis de fotos y reportes",
    }
    for n in faltan:
        print(f"\n[ASISTENTE] *** FALTA {n} en .env — afecta: {para[n]}.", flush=True)
    if faltan:
        print("[ASISTENTE] El asistente sigue con los proveedores restantes y respuestas locales. "
              "SOS y navegación NO dependen de keys.\n", flush=True)
    return faltan
