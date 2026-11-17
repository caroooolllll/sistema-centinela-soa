"""Cifrado del vector facial con Fernet. La llave (BIOMETRIA_KEY) es distinta de SECRET_KEY y vive solo en .env."""
import os

import numpy as np
from cryptography.fernet import Fernet, InvalidToken


class BiometriaKeyError(RuntimeError):
    pass


def _fernet():
    k = os.getenv('BIOMETRIA_KEY', '').strip()
    if not k:
        raise BiometriaKeyError(
            "Falta BIOMETRIA_KEY en .env. Genérala con: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    try:
        return Fernet(k.encode())
    except Exception:
        raise BiometriaKeyError("BIOMETRIA_KEY inválida: debe ser una llave Fernet (44 caracteres base64).")


def normalizar(vec):
    v = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(v))
    if not np.isfinite(n) or n == 0:
        raise ValueError("vector inválido")
    return v / n


def cifrar_vector(vec):
    return _fernet().encrypt(normalizar(vec).tobytes())


def descifrar_vector(blob):
    try:
        return np.frombuffer(_fernet().decrypt(bytes(blob)), dtype=np.float32)
    except InvalidToken:
        raise BiometriaKeyError("No se pudo descifrar: BIOMETRIA_KEY distinta a la usada al registrar.")


def avisar_si_falta_key():
    if not os.getenv('BIOMETRIA_KEY', '').strip():
        print("\n[BIOMETRIA] *** FALTA BIOMETRIA_KEY en .env — el registro/verificación facial no funcionará "
              "hasta que la agregues (ver .env.example).\n", flush=True)
