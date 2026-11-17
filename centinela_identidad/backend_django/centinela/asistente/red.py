"""Detección rápida de internet (para no esperar timeouts de DNS/red cuando no hay conexión)."""
import socket
import time

from . import config

_cache = {"hasta": 0.0, "ok": True}


def hay_internet():
    """True/False con caché corta. ASISTENTE_FORZAR_OFFLINE=true simula 'sin internet' (para pruebas)."""
    if config.env("ASISTENTE_FORZAR_OFFLINE").lower() in ("1", "true", "si"):
        return False
    ahora = time.monotonic()
    if ahora < _cache["hasta"]:
        return _cache["ok"]
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=0.8).close()
        ok = True
    except OSError:
        ok = False
    _cache.update(hasta=ahora + (8 if ok else 3), ok=ok)
    return ok
