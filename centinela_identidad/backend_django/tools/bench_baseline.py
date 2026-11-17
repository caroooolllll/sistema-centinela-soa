"""Mide el asistente ACTUAL (/api/ia/asistente/, sin streaming). Uso: python tools/bench_baseline.py"""
import time, json, httpx
PREGUNTAS = [
    "abre reportes",
    "¿qué pasó hoy en la privada?",
    "prepara un reporte de que hay un árbol caído en calle Rosas",
    "¿cómo cambio mi foto de perfil?",
    "me están robando, ayuda",
]
with httpx.Client(timeout=60) as c:
    for q in PREGUNTAS:
        t = time.perf_counter()
        try:
            r = c.post("http://127.0.0.1:9000/api/ia/asistente/", json={"mensaje": q})
            dt = time.perf_counter() - t
            d = r.json()
            print(f"{dt:6.2f}s  http={r.status_code} tipo={d.get('tipo')} | {q} -> {str(d.get('respuesta') or d.get('error'))[:70]}")
        except Exception as e:
            print(f"ERR {q}: {e}")
