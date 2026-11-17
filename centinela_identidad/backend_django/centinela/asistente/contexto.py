"""Contexto de la privada para preguntas tipo '¿qué pasó hoy?' (avisos/incidencias del SDRI)."""
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import httpx

from . import config
from .atajos import normalizar

# Solo preguntas sobre lo que ocurre ("qué pasó", "hay avisos", "novedades"), no peticiones de crear algo
_DISPARADORES = re.compile(
    r"\b(que (paso|pasa|hay|ocurrio|sucedio|ha pasado)|novedades?|avisos?|incidencias?|"
    r"hoy|ayer|ultimos?|recientes?|alertas?|como esta (la )?(privada|seguridad))\b")
_CREAR = re.compile(r"^(crea|haz|hacer|prepara|preparame|genera|publica|manda|escribe|agenda|programa|registra)\b")

_cache = {"t": 0.0, "datos": ""}
_TTL_OK = 20.0       # el resultado se reutiliza 20 s
_TTL_FALLO = 30.0    # si el SDRI está caído no se reintenta en 30 s (no frena al asistente)


def _limpio(t):
    from automatizacion.servicios import sanitizar_dato
    return sanitizar_dato(t, 120)


def necesita_contexto(texto):
    n = normalizar(texto)
    return bool(_DISPARADORES.search(n)) and not _CREAR.search(n)


def avisos_recientes(max_items=8, dias=3):
    """Texto compacto con incidencias recientes, o '' si el SDRI no responde (no bloquea al asistente)."""
    ahora = time.monotonic()
    if ahora < _cache["t"]:
        return _cache["datos"]
    try:
        url = config.sdri_url().replace("localhost", "127.0.0.1")  # evita la espera de IPv6 en Windows
        r = httpx.get(f"{url}/api/consultar_incidencias", timeout=httpx.Timeout(1.0, connect=0.3))
        raiz = ET.fromstring(r.content)
    except Exception:
        _cache.update(t=ahora + _TTL_FALLO, datos="")
        return ""
    limite = date.today() - timedelta(days=dias)
    filas = []
    for it in raiz.findall("incidencia"):
        g = lambda t: (it.findtext(t) or "").strip()
        try:
            f = datetime.strptime(g("fecha"), "%Y-%m-%d").date()
        except ValueError:
            f = None
        if f and f < limite:
            continue
        filas.append(f"- {g('fecha')} {g('hora')[:5]} [{g('prioridad')}] {g('tipo')}: {_limpio(g('descripcion'))} ({g('estado')})")
        if len(filas) >= max_items:
            break
    datos = "\n".join(filas)
    _cache.update(t=ahora + _TTL_OK, datos=datos)
    return datos
