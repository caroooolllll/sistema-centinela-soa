"""
Validadores de datos para los endpoints de contactos de emergencia.
Sin DRF — mantiene la convención del proyecto (JsonResponse puro).
"""
from .models import RELACION_CHOICES

_RELACION_VALS = {r[0] for r in RELACION_CHOICES}


def validar_contacto(data: dict, parcial: bool = False) -> tuple:
    """
    Valida datos de ContactoEmergencia.
    Returns: (datos_limpios: dict, errores: list[str])
    """
    errores = []
    limpio  = {}

    if not parcial or 'nombre_contacto' in data:
        nombre = str(data.get('nombre_contacto', '')).strip()
        if not nombre:
            errores.append('nombre_contacto es requerido')
        elif len(nombre) > 100:
            errores.append('nombre_contacto: máximo 100 caracteres')
        else:
            limpio['nombre_contacto'] = nombre

    if not parcial or 'relacion' in data:
        rel = str(data.get('relacion', 'otro')).strip()
        limpio['relacion'] = rel if rel in _RELACION_VALS else 'otro'

    if 'numero_telefono' in data:
        tel = str(data.get('numero_telefono', '')).strip()
        if len(tel) > 20:
            errores.append('numero_telefono: máximo 20 caracteres')
        else:
            limpio['numero_telefono'] = tel

    return limpio, errores
