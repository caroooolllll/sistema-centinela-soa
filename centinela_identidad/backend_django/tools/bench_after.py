"""Mide el pipeline NUEVO (/api/ia/asistente/stream/ + /api/ia/tts/).
Uso: python tools/bench_after.py
 - primer texto : llegada del primer evento 'frase'
 - empieza voz  : primer texto + tiempo en que edge-tts devuelve el audio de esa primera oración
                  (el navegador pide la voz en cuanto llega la frase, igual que aquí)
 - total        : hasta recibir 'fin' y todo el audio de las oraciones
Los atajos (navegación / SOS) se resuelven en el navegador sin red: se mide el atajo local en Node.
"""
import json
import os
import shutil
import subprocess
import time
import concurrent.futures as cf

import httpx

BASE = "http://127.0.0.1:9000"
PREGUNTAS = [
    "abre reportes",
    "¿qué pasó hoy en la privada?",
    "prepara un reporte de que hay un árbol caído en calle Rosas",
    "¿cómo cambio mi foto de perfil?",
    "me están robando, ayuda",
]


NODE = shutil.which("node") or "C:/Program Files/nodejs/node.exe"


def atajo_local_ms(texto):
    """Tiempo del atajo del navegador (Node ejecuta el mismo asistente-atajos.js)."""
    js = ("const A=require('../frontend/js/asistente-atajos.js');const t=process.hrtime.bigint();"
          "const r=A.resolver(process.argv[1]);const ms=Number(process.hrtime.bigint()-t)/1e6;"
          "console.log(JSON.stringify({r:r&&r.tipo,ms}))")
    out = subprocess.run([NODE, "-e", js, texto], capture_output=True, text=True, cwd=".").stdout
    return json.loads(out) if out.strip() else None


def tts_ms(c, texto):
    t = time.perf_counter()
    r = c.post(f"{BASE}/api/ia/tts/", json={"texto": texto}, timeout=20)
    return (time.perf_counter() - t) * 1000, r.status_code


def main():
    with httpx.Client(timeout=60) as c:
        for q in PREGUNTAS:
            loc = atajo_local_ms(q)
            if loc and loc["r"]:
                print(f"{q!r:70} ATAJO LOCAL ({loc['r']}) {loc['ms']:.2f} ms — sin red, sin LLM")
                continue
            t0 = time.perf_counter()
            primer = voz = None
            prov = "?"
            pool = cf.ThreadPoolExecutor(4)
            futs = []
            with c.stream("POST", f"{BASE}/api/ia/asistente/stream/", json={"mensaje": q}) as r:
                evento = None
                for linea in r.iter_lines():
                    if linea.startswith("event:"):
                        evento = linea[6:].strip()
                    elif linea.startswith("data:"):
                        d = json.loads(linea[5:])
                        if evento == "frase":
                            if primer is None:
                                primer = (time.perf_counter() - t0) * 1000
                            futs.append((time.perf_counter(), pool.submit(tts_ms, httpx.Client(timeout=30), d["texto"])))
                        elif evento == "fin":
                            prov = d.get("proveedor")
            audio_listo = []
            for ini, f in futs:
                ms, st = f.result()
                audio_listo.append(((ini - t0) * 1000) + ms)
            if audio_listo:
                voz = audio_listo[0]
            total = (time.perf_counter() - t0) * 1000
            print(f"{q!r:70} primer texto {primer:7.0f} ms | empieza voz {voz or 0:7.0f} ms | total {total:7.0f} ms | {prov}")


if __name__ == "__main__":
    main()
