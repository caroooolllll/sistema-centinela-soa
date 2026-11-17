"""Comparación de plantillas por similitud coseno (vectores normalizados => producto punto)."""
import os

import numpy as np

from .crypto import descifrar_vector, normalizar
from .models import PlantillaFacial


def dim_esperada():
    return int(os.getenv('BIOMETRIA_DIM', '128'))


def umbral():
    """Similitud coseno mínima para aceptar (más alto = más estricto). Ver docs/BIOMETRIA.md."""
    return float(os.getenv('BIOMETRIA_UMBRAL', '0.90'))


def margen():
    """Para 1:N: el mejor candidato debe superar al segundo (de otro usuario) por al menos este margen."""
    return float(os.getenv('BIOMETRIA_MARGEN', '0.03'))


def validar_vector(v):
    """→ np.ndarray normalizado o ValueError."""
    if not isinstance(v, (list, tuple)) or len(v) != dim_esperada():
        raise ValueError(f"El vector debe tener {dim_esperada()} valores")
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        raise ValueError("El vector solo puede contener números")
    return normalizar(v)


def similitud(a, b):
    return float(np.dot(a, b))


def verificar_1a1(usuario, vector):
    """→ (coincide, score) contra la plantilla de ESE usuario. Sin plantilla: (False, None)."""
    try:
        p = PlantillaFacial.objects.get(usuario=usuario)
    except PlantillaFacial.DoesNotExist:
        return False, None
    s = similitud(vector, descifrar_vector(p.vector_cifrado))
    return s >= umbral(), s


def identificar_1aN(vector):
    """→ (usuario|None, mejor_score, segundo_score). Ambigüedades (margen chico) cuentan como no reconocido."""
    puntajes = []
    for p in PlantillaFacial.objects.select_related('usuario__casa').all():
        puntajes.append((similitud(vector, descifrar_vector(p.vector_cifrado)), p.usuario))
    if not puntajes:
        return None, None, None
    puntajes.sort(key=lambda t: t[0], reverse=True)
    mejor = puntajes[0]
    segundo = puntajes[1][0] if len(puntajes) > 1 else None
    if mejor[0] < umbral():
        return None, mejor[0], segundo
    if segundo is not None and (mejor[0] - segundo) < margen():
        return None, mejor[0], segundo
    return mejor[1], mejor[0], segundo
