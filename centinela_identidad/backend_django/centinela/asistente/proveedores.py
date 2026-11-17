"""Proveedores de LLM con streaming y cadena de respaldo.

Groq -> Gemini Flash -> Claude -> respuestas locales (orden configurable: ASISTENTE_CADENA).

Distinción de 429:
  * 'minuto'  (TPM/RPM): se espera poco (Retry-After, máx ASISTENTE_ESPERA_429_MAX s) y se reintenta UNA vez.
  * 'diario'  (TPD/RPD/cuota) o espera demasiado larga: salta de inmediato al siguiente proveedor.
Si un proveedor falla antes de emitir texto, se pasa al siguiente. Si falla a mitad de la
respuesta se conserva lo ya emitido (no se mezclan dos modelos en una misma respuesta).
"""
import json
import re
import time
import logging

import httpx

from . import config
from .parser import MARCA

log = logging.getLogger("centinela.asistente")

TIMEOUT = httpx.Timeout(20.0, connect=4.0)


class ProveedorError(Exception):
    """kind: 'minuto' | 'diario' | 'auth' | 'otro'."""

    def __init__(self, kind, msg="", retry_after=None):
        super().__init__(msg)
        self.kind = kind
        self.retry_after = retry_after


_DIARIO = re.compile(r"per day|\bTPD\b|\bRPD\b|PerDay|daily|quota exceeded|exceeded your current quota|"
                     r"insufficient[_ ]quota|credit balance|billing", re.I)


def clasificar_429(texto, retry_after=None):
    """Devuelve 'diario' o 'minuto' para una respuesta 429."""
    if _DIARIO.search(texto or ""):
        return "diario"
    if retry_after is not None and retry_after > config.espera_429_max():
        return "diario"  # esperar tanto no vale la pena: se trata como agotado
    return "minuto"


def _retry_after(headers):
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _error_http(resp_status, cuerpo, headers):
    if resp_status == 429:
        ra = _retry_after(headers)
        return ProveedorError(clasificar_429(cuerpo, ra), f"429: {cuerpo[:160]}", ra)
    if resp_status in (401, 403):
        return ProveedorError("auth", f"HTTP {resp_status} (revisa la key en .env)")
    return ProveedorError("otro", f"HTTP {resp_status}: {cuerpo[:160]}")


# ── Groq ─────────────────────────────────────────────────────────────
def stream_groq(system, mensajes, max_tokens=700):
    k = config.key("GROQ_API_KEY")
    if not k:
        raise ProveedorError("auth", "GROQ_API_KEY no configurada")
    body = {"model": config.groq_modelo(), "stream": True, "temperature": 0.3, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}] + mensajes}
    try:
        with httpx.stream("POST", "https://api.groq.com/openai/v1/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {k}"}, timeout=TIMEOUT) as r:
            if r.status_code != 200:
                r.read()
                raise _error_http(r.status_code, r.text, r.headers)
            for linea in r.iter_lines():
                if not linea.startswith("data:"):
                    continue
                dato = linea[5:].strip()
                if dato == "[DONE]":
                    return
                try:
                    delta = json.loads(dato)["choices"][0]["delta"].get("content")
                except (ValueError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
    except httpx.HTTPError as e:
        raise ProveedorError("otro", f"red: {type(e).__name__}")


# ── Gemini ───────────────────────────────────────────────────────────
def stream_gemini(system, mensajes, max_tokens=700):
    k = config.key("GEMINI_API_KEY")
    if not k:
        raise ProveedorError("auth", "GEMINI_API_KEY no configurada")
    contenido = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                 for m in mensajes]
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contenido,
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.gemini_modelo()}:streamGenerateContent?alt=sse"
    try:
        with httpx.stream("POST", url, json=body, headers={"x-goog-api-key": k}, timeout=TIMEOUT) as r:
            if r.status_code != 200:
                r.read()
                raise _error_http(r.status_code, r.text, r.headers)
            for linea in r.iter_lines():
                if not linea.startswith("data:"):
                    continue
                try:
                    partes = json.loads(linea[5:].strip())["candidates"][0]["content"]["parts"]
                except (ValueError, KeyError, IndexError):
                    continue
                for p in partes:
                    if p.get("text"):
                        yield p["text"]
    except httpx.HTTPError as e:
        raise ProveedorError("otro", f"red: {type(e).__name__}")


# ── Claude (integración existente, se queda como respaldo) ───────────
def stream_claude(system, mensajes, max_tokens=700):
    k = config.key("ANTHROPIC_API_KEY")
    if not k:
        raise ProveedorError("auth", "ANTHROPIC_API_KEY no configurada")
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=k, timeout=25.0, max_retries=0)
        with client.messages.stream(model=config.claude_modelo(), max_tokens=max_tokens,
                                    system=system, messages=mensajes) as s:
            for t in s.text_stream:
                yield t
    except anthropic.RateLimitError as e:
        ra = _retry_after(getattr(getattr(e, "response", None), "headers", {}) or {})
        raise ProveedorError(clasificar_429(str(e), ra), "429 Claude", ra)
    except anthropic.AuthenticationError:
        raise ProveedorError("auth", "ANTHROPIC_API_KEY inválida")
    except anthropic.APIError as e:
        raise ProveedorError("otro", f"Claude: {type(e).__name__}")


# ── Local (último recurso, sin red) ──────────────────────────────────
def stream_local(system, mensajes, max_tokens=0):
    ultimo = mensajes[-1]["content"] if mensajes else ""
    from .atajos import normalizar
    n = normalizar(ultimo)
    if any(p in n for p in ("reporte", "incidencia", "robo", "vandal", "fuga", "arbol")):
        txt = ("Ahora mismo no tengo conexión con la inteligencia artificial, pero puedes crear tu reporte "
               "en la sección de reportes.")
        accion = {"tipo": "navegacion", "destino": "avisos.html"}
    else:
        txt = ("Ahora mismo no tengo conexión con la inteligencia artificial. Aún puedo abrir secciones, "
               "por ejemplo di: abre eventos. Y si hay una emergencia, di: auxilio.")
        accion = {"tipo": "respuesta", "destino": None}
    yield txt + "\n" + MARCA + "\n" + json.dumps(accion)


PROVEEDORES = {"groq": stream_groq, "gemini": stream_gemini, "claude": stream_claude, "local": stream_local}


class Cadena:
    """Ejecuta la cadena de respaldo. Uso: for chunk in Cadena().stream(system, mensajes)."""

    def __init__(self, orden=None, sleep=time.sleep):
        self.orden = orden or config.cadena()
        self.sleep = sleep
        self.proveedor = None      # quién respondió
        self.intentos = []         # [(nombre, resultado)] para el log / UI de demo

    def stream(self, system, mensajes, max_tokens=700):
        for nombre in self.orden:
            fn = PROVEEDORES.get(nombre)
            if not fn:
                continue
            reintento = False
            while True:
                emitio = False
                try:
                    for chunk in fn(system, mensajes, max_tokens):
                        if not emitio:
                            self.proveedor = nombre
                            emitio = True
                        yield chunk
                    if emitio:
                        self.intentos.append((nombre, "ok"))
                        return
                    self.intentos.append((nombre, "vacío"))
                    break
                except ProveedorError as e:
                    if emitio:  # falló a mitad: nos quedamos con lo emitido
                        log.warning("[asistente] %s se cortó a mitad: %s", nombre, e.kind)
                        self.intentos.append((nombre, f"cortado:{e.kind}"))
                        return
                    if e.kind == "minuto" and not reintento:
                        espera = min(e.retry_after if e.retry_after is not None else 1.0,
                                     config.espera_429_max())
                        log.warning("[asistente] %s 429/minuto: espero %.1fs y reintento", nombre, espera)
                        self.sleep(espera)
                        reintento = True
                        continue
                    log.warning("[asistente] %s falló (%s) -> siguiente proveedor", nombre, e.kind)
                    self.intentos.append((nombre, e.kind))
                    break
        self.proveedor = None

    def completar(self, system, mensajes, max_tokens=500):
        """Versión sin streaming: devuelve (texto, proveedor). Para extracción de JSON."""
        texto = "".join(self.stream(system, mensajes, max_tokens))
        return texto, self.proveedor
