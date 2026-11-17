"""Atajos locales sin LLM: SOS y navegación.
Espejo en frontend/js/asistente-atajos.js (el frontend es quien lo ejecuta primero, sin red)."""
import re
import unicodedata

NAV_PAGINAS = {
    "dashboard.html": ["dashboard", "inicio", "panel", "home", "principal", "tablero"],
    "chat.html": ["chat", "mensajes", "conversaciones", "chat vecinal"],
    "eventos.html": ["eventos", "evento", "agenda", "actividades", "calendario"],
    "noticias.html": ["noticias", "noticia", "novedades"],
    "avisos.html": ["avisos", "aviso", "reportes", "reporte", "incidencias", "incidencia", "tablon", "comunicados"],
    "encuestas.html": ["encuestas", "encuesta", "votaciones", "votacion", "decisiones"],
    "historial.html": ["historial", "reportes anteriores", "reportes pasados"],
    "panico.html": ["panico", "boton de panico"],
    "accesibilidad-modo.html": ["accesibilidad", "modo accesible", "modo accesibilidad"],
    "perfil.html": ["perfil", "mi perfil", "mi cuenta", "cuenta"],
    "configuracion.html": ["configuracion", "ajustes", "opciones"],
    "notificaciones.html": ["notificaciones", "notificacion", "alertas"],
    "publicaciones.html": ["publicaciones", "publicacion", "posts", "foros", "foro"],
    "emergencia-contactos.html": ["contactos de emergencia", "contactos", "directorio", "directorio de emergencia"],
    "porton.html": ["porton", "porton inteligente", "puerta", "acceso facial", "camara de acceso"],
    "centro-mando.html": ["centro de mando", "panel de control", "mando"],
    "visitas.html": ["mis visitas", "visitas", "qr de visita", "invitados"],
}
NOMBRES = {
    "dashboard.html": "el inicio", "chat.html": "el chat", "eventos.html": "los eventos",
    "noticias.html": "las noticias", "avisos.html": "los reportes y avisos",
    "encuestas.html": "las encuestas", "historial.html": "el historial",
    "panico.html": "el botón de pánico", "accesibilidad-modo.html": "accesibilidad",
    "perfil.html": "tu perfil", "configuracion.html": "la configuración",
    "notificaciones.html": "las notificaciones", "publicaciones.html": "las publicaciones",
    "emergencia-contactos.html": "los contactos de emergencia",
    "porton.html": "el portón inteligente",
    "centro-mando.html": "el centro de mando",
    "visitas.html": "tus visitas con QR",
}
VERBOS_NAV = [
    "abre", "abrir", "abreme", "ve a", "ve al", "vete a", "ir a", "ir al", "llevame a", "llevame al",
    "llevame", "muestrame", "mostrar", "quiero ver", "quiero ir a", "quiero ir al", "navega a",
    "navegar a", "dame", "entra a", "entrar a", "pasa a", "regresa a", "vuelve a", "vamos a", "enseñame",
]
RELLENO = {"el", "la", "los", "las", "un", "una", "mi", "mis", "de", "del", "a", "al", "pagina", "pantalla",
           "seccion", "modulo", "ventana", "por", "favor", "porfa", "ya", "ahora", "quiero", "me", "puedes",
           "podrias", "oye", "en", "lo", "que", "es", "sea", "vecinal", "vecinos"}

# ── SOS ──────────────────────────────────────────────────────────────
SOS_PATRONES = [
    r"\bauxilio\b", r"\bsocorro\b", r"\bsos\b",
    r"\bme estan (robando|asaltando|atacando|siguiendo|golpeando)\b",
    r"\bme (quieren|intentan) (robar|asaltar|atacar|secuestrar)\b",
    r"\bme (robaron|asaltaron|asaltan|roban)\b",
    r"\bnecesito ayuda\b",
    r"\b(pide|pidan|llama|llamen|llamar)( a)?( la| el)? (ayuda|policia|ambulancia|emergencias|seguridad)\b",
    r"\bhay (un |una )?(ladron|ladrones|intruso|incendio|fuego|herido|heridos|balacera|disparos)\b",
    r"\bentraron (a|en) mi (casa|domicilio)\b", r"\b(disparos|balacera)\b",
    r"\bactiva(r)? (el |la )?(sos|emergencia|panico|alerta)\b",
    r"\b(estoy|esta) en peligro\b", r"\bayuda (urgente|por favor|porfavor)\b",
    r"\bes una emergencia\b", r"\bemergencia\b",
]
# Frases con palabras de emergencia que NO son una emergencia
SOS_EXCLUIR = [r"contactos? de emergencia", r"directorio de emergencia", r"\b(como|que) (es|funciona|activo|hago)\b",
               r"\bsimulacro\b", r"\bpara que sirve\b", r"\bconfigur"]
_SOS_RE = [re.compile(p) for p in SOS_PATRONES]
_EXCL_RE = [re.compile(p) for p in SOS_EXCLUIR]


def normalizar(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def quitar_activacion(t):
    n = normalizar(t)
    i = n.find("centinela")
    return n[i + 9:].strip() if i >= 0 else n


def es_sos(texto):
    n = quitar_activacion(texto)
    if not n:
        return False
    if any(r.search(n) for r in _EXCL_RE):
        return False
    if any(r.search(n) for r in _SOS_RE):
        return True
    # "ayuda" suelta (<=3 palabras) -> SOS. "ayúdame a crear un reporte" NO.
    palabras = n.split()
    return len(palabras) <= 3 and "ayuda" in palabras


def detectar_navegacion(texto):
    """(destino, frase) o None. Solo si TODO el comando es verbo + página + relleno."""
    n = quitar_activacion(texto)
    if not n:
        return None
    resto = None
    for v in sorted(VERBOS_NAV, key=len, reverse=True):
        v = normalizar(v)
        if n == v or n.startswith(v + " "):
            resto = n[len(v):].strip()
            break
    if resto is None:
        return None
    mejor = None
    for destino, sinonimos in NAV_PAGINAS.items():
        for s in sinonimos:
            if re.search(rf"(^|\s){re.escape(s)}(\s|$)", resto):
                if mejor is None or len(s) > len(mejor[1]):
                    mejor = (destino, s)
    if not mejor:
        return None
    sobrante = re.sub(rf"(^|\s){re.escape(mejor[1])}(\s|$)", " ", resto).split()
    if any(p not in RELLENO for p in sobrante):
        return None
    return mejor[0], f"Abriendo {NOMBRES[mejor[0]]}."


def resolver_atajo(texto):
    """Acción lista (contrato del frontend) o None si debe ir al LLM."""
    if es_sos(texto):
        return {"tipo": "emergencia", "destino": "panico.html", "activar_sos": True,
                "respuesta": "Activando emergencia ahora. Mantén la calma, abro el botón de pánico."}
    nav = detectar_navegacion(texto)
    if nav:
        return {"tipo": "navegacion", "destino": nav[0], "respuesta": nav[1]}
    return None
