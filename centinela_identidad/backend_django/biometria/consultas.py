"""Respuestas del asistente de voz a partir de la bitácora de accesos (SOLO LECTURA, según el rol)."""
import re
from datetime import timedelta

from django.utils import timezone

from centinela.asistente.atajos import normalizar

from .models import BitacoraAcceso, VisitaPendiente

_QUIEN = re.compile(r"\b(quien|quienes)\b.*\b(entro|entraron|entra|llego|llegaron|paso por)\b|\baccesos? (de )?hoy\b|"
                    r"\b(ultimo|ultimos) accesos?\b|\bbitacora de accesos\b")
_VISITAS = re.compile(r"\bvisitantes?\b|\bvisitas?\b.*\b(no registrad|pendiente)|\bgente (desconocida|extrana)\b|"
                      r"\bdesconocid[oa]s?\b")


def _hoy():
    ahora = timezone.localtime()
    return ahora.replace(hour=0, minute=0, second=0, microsecond=0)


def _hora(dt):
    return timezone.localtime(dt).strftime('%H:%M')


def responder_bitacora(texto, usuario):
    """→ texto hablado, o None si la pregunta no es sobre accesos. `usuario` puede ser None (sin sesión)."""
    n = normalizar(texto)
    quien, visitas = bool(_QUIEN.search(n)), bool(_VISITAS.search(n))
    if not (quien or visitas):
        return None
    if usuario is None:
        return "Para consultar la bitácora de accesos necesito que inicies sesión."
    admin = usuario.email == 'admin@centinela.com'
    inicio = _hoy()
    base = BitacoraAcceso.objects.filter(fecha__gte=inicio)

    if visitas:
        if not admin:
            return "La información de visitantes no registrados solo la ve el administrador o la caseta."
        v = VisitaPendiente.objects.filter(fecha__gte=inicio).order_by('-fecha')
        total = v.count()
        if total == 0:
            return "Hoy no hubo visitantes no registrados."
        pend = v.filter(estado='pendiente').count()
        ultima = _hora(v.first().fecha)
        return (f"Hoy hubo {total} visitante{'s' if total != 1 else ''} no registrado{'s' if total != 1 else ''}, "
                f"{pend} pendiente{'s' if pend != 1 else ''} de atender. El último llegó a las {ultima}.")

    accesos = base.filter(evento='acceso', resultado='ok')
    if not admin:
        accesos = accesos.filter(usuario=usuario)
        total = accesos.count()
        if total == 0:
            return "Hoy no tienes accesos registrados en el portón. Solo puedo mostrarte los tuyos."
        return f"Hoy tuviste {total} acceso{'s' if total != 1 else ''} por el portón; el último a las {_hora(accesos.first().fecha)}."
    total = accesos.count()
    if total == 0:
        return "Hoy no hay accesos de vecinos registrados en el portón."
    nombres = []
    for a in accesos[:20]:
        etiqueta = f"{a.nombre.split(' (')[0]} de {a.casa}"
        if etiqueta not in nombres:
            nombres.append(etiqueta)
    lista = ", ".join(nombres[:4]) + (" y otros" if len(nombres) > 4 else "")
    return f"Hoy entraron {total} {'vez' if total == 1 else 'veces'}: {lista}. El último acceso fue a las {_hora(accesos.first().fecha)}."
