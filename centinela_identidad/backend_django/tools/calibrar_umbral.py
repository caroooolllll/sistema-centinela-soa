"""Mini calibración FAR/FRR del umbral facial.
Entrada: JSON exportado desde frontend/calibracion-biometria.html
         {"personas": {"Ana": [[128 valores], ...], "Luis": [[...], ...]}}
Uso:     python tools/calibrar_umbral.py capturas.json [--far-max 0.01]
Salida:  tabla FAR/FRR por umbral, EER y el umbral recomendado (el MÁS BAJO con FAR <= far-max,
         para rechazar lo mínimo posible a los vecinos reales)."""
import argparse
import itertools
import json

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--far-max", type=float, default=0.01)
    a = ap.parse_args()
    personas = {n: np.array([v / np.linalg.norm(v) for v in map(np.array, vs)]) for n, vs in
                json.load(open(a.archivo, encoding="utf-8"))["personas"].items()}
    gen, imp = [], []
    for n, m in personas.items():
        gen += [float(m[i] @ m[j]) for i, j in itertools.combinations(range(len(m)), 2)]
    for (n1, m1), (n2, m2) in itertools.combinations(personas.items(), 2):
        imp += [float(x @ y) for x in m1 for y in m2]
    gen, imp = np.array(gen), np.array(imp)
    print(f"Pares genuinos: {len(gen)} · pares impostores: {len(imp)}")
    if len(gen) < 20 or len(imp) < 20:
        print("AVISO: muy pocos pares; captura >= 3 personas con >= 8 capturas cada una (con distinta pose/luz).")
    print("umbral   FAR (falsos aceptados)   FRR (falsos rechazados)")
    mejor, eer = None, (9, 0)
    for t in np.arange(0.70, 0.99, 0.01):
        far, frr = float((imp >= t).mean()), float((gen < t).mean())
        print(f"{t:5.2f}   {far:8.2%}               {frr:8.2%}")
        if abs(far - frr) < eer[0]:
            eer = (abs(far - frr), t, (far + frr) / 2)
        if mejor is None and far <= a.far_max:
            mejor = (t, far, frr)
    print(f"\nEER ~ {eer[2]:.2%} en umbral {eer[1]:.2f}")
    if mejor:
        print(f"RECOMENDADO (FAR <= {a.far_max:.0%}): BIOMETRIA_UMBRAL={mejor[0]:.2f}  (FAR {mejor[1]:.2%}, FRR {mejor[2]:.2%})")
    else:
        print("Ningún umbral cumple el FAR pedido: captura mejores datos o sube el rango.")


if __name__ == "__main__":
    main()
