"""API de biometría facial. Todo JSON. Nunca se recibe ni se guarda una foto: solo el vector."""
import json
import time
from collections import defaultdict, deque

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from auth_app.models import Sesion, Usuario
from centinela.asistente import feria

from . import matching
from .crypto import BiometriaKeyError, cifrar_vector
from .models import BitacoraAcceso, PlantillaFacial, VisitaPendiente

ADMIN_EMAIL = 'admin@centinela.com'
DEMO_DOMINIO = '@demo.centinela.local'

# ── utilidades ───────────────────────────────────────────────────────
_golpes = defaultdict(deque)


def _limitado(request, clave, max_por_min=30):
    ip = request.META.get('REMOTE_ADDR', '?')
    q = _golpes[(ip, clave)]
    ahora = time.monotonic()
    while q and ahora - q[0] > 60:
        q.popleft()
    if len(q) >= max_por_min:
        return True
    q.append(ahora)
    return False


def _json(request):
    try:
        d = json.loads(request.body or b'{}')
        return d if isinstance(d, dict) else {}
    except ValueError:
        return None


def es_demo_usuario(u):
    return bool(u) and u.email.endswith(DEMO_DOMINIO)


def es_admin(u):
    return bool(u) and u.email == ADMIN_EMAIL


def _sesion(request, permitir_pendiente=False):
    h = request.META.get('HTTP_AUTHORIZATION', '')
    if not h.startswith('Token '):
        return None
    filtros = dict(token=h[6:], activa=True, fecha_expiracion__gt=timezone.now())
    if not permitir_pendiente:
        filtros['biometria_pendiente'] = False
    try:
        return Sesion.objects.select_related('usuario__casa').get(**filtros)
    except Sesion.DoesNotExist:
        return None


def _log(usuario, evento, resultado, origen, score=None, detalle='', demo=False):
    b = BitacoraAcceso.objects.create(
        usuario=usuario, nombre=usuario.nombre_completo if usuario else '',
        casa=usuario.casa.numero_casa if usuario and usuario.casa else '',
        evento=evento, resultado=resultado, origen=origen,
        score=None if score is None else round(float(score), 4),
        detalle=detalle[:300], es_demo=bool(demo or es_demo_usuario(usuario)))
    from automatizacion import cadena           # cadena de hash: cada evento sella al anterior
    cadena.sellar_bitacora(b)
    try:
        from automatizacion import servicios    # reglas + alertas de anomalías (nunca deben romper el flujo)
        servicios.al_registrar_acceso(b)
    except Exception:
        pass
    return b


def _err(msg, status=400, **extra):
    return JsonResponse({'estado': 'ERROR', 'mensaje': msg, **extra}, status=status)


def _vector(d):
    try:
        return matching.validar_vector(d.get('vector')), None
    except ValueError as e:
        return None, _err(str(e))


def _exigir_vida(d, usuario, origen):
    if d.get('liveness_ok') is not True:
        _log(usuario, 'verificacion', 'denegado', origen, detalle='sin prueba de vida')
        return _err('Se requiere la prueba de vida', 403)
    return None


# ── endpoints ────────────────────────────────────────────────────────
def config(request):
    return JsonResponse({'modo_feria': feria.activo(), 'dim': matching.dim_esperada()})


def estado(request):
    s = _sesion(request, permitir_pendiente=True)
    if not s:
        return _err('Sesión requerida', 401)
    try:
        p = PlantillaFacial.objects.get(usuario=s.usuario)
        return JsonResponse({'registrada': True, 'creado': p.creado.isoformat(), 'es_demo': p.es_demo,
                             'pendiente': s.biometria_pendiente, 'modo_feria': feria.activo()})
    except PlantillaFacial.DoesNotExist:
        return JsonResponse({'registrada': False, 'pendiente': s.biometria_pendiente, 'modo_feria': feria.activo()})


@csrf_exempt
def registrar(request):
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    s = _sesion(request)
    if not s:
        return _err('Sesión requerida', 401)
    d = _json(request)
    if d is None:
        return _err('JSON inválido')
    if d.get('consentimiento') is not True:
        return _err('Debes aceptar el aviso de privacidad para registrar tu rostro', 400)
    v, e = _vector(d)
    if e:
        return e
    err = _exigir_vida(d, s.usuario, 'perfil')
    if err:
        return err
    try:
        blob = cifrar_vector(v)
    except BiometriaKeyError as ex:
        return _err(str(ex), 500)
    PlantillaFacial.objects.update_or_create(
        usuario=s.usuario, defaults={'vector_cifrado': blob, 'dim': len(v), 'es_demo': es_demo_usuario(s.usuario)})
    _log(s.usuario, 'registro', 'ok', 'perfil', detalle='consentimiento aceptado')
    return JsonResponse({'estado': 'OK', 'mensaje': 'Rostro registrado'})


@csrf_exempt
def verificar(request):
    """1:1 — segundo factor al iniciar sesión y confirmación de acciones críticas."""
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    if _limitado(request, 'verificar', 20):
        return _err('Demasiados intentos, espera un minuto', 429)
    s = _sesion(request, permitir_pendiente=True)
    if not s:
        return _err('Sesión requerida', 401)
    d = _json(request)
    if d is None:
        return _err('JSON inválido')
    origen = d.get('origen') if d.get('origen') in ('login', 'accion_critica', 'perfil') else 'accion_critica'
    v, e = _vector(d)
    if e:
        return e
    err = _exigir_vida(d, s.usuario, origen)
    if err:
        return err
    try:
        ok, score = matching.verificar_1a1(s.usuario, v)
    except BiometriaKeyError as ex:
        return _err(str(ex), 500)
    if score is None:
        return _err('No tienes rostro registrado', 404)
    _log(s.usuario, 'verificacion', 'ok' if ok else 'denegado', origen, score,
         detalle=str(d.get('accion', ''))[:100])
    if ok and s.biometria_pendiente:
        s.biometria_pendiente = False
        s.save(update_fields=['biometria_pendiente'])
    return JsonResponse({'estado': 'OK', 'coincide': ok, 'score': round(score, 4)})


@csrf_exempt
def omitir(request):
    """Solo modo feria: libera una sesión pendiente si la cámara falla en plena demo (queda en la bitácora)."""
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    if not feria.activo():
        return _err('Solo disponible en modo feria', 403)
    s = _sesion(request, permitir_pendiente=True)
    if not s:
        return _err('Sesión requerida', 401)
    if s.biometria_pendiente:
        s.biometria_pendiente = False
        s.save(update_fields=['biometria_pendiente'])
    _log(s.usuario, 'verificacion', 'ok', 'login', detalle='OMITIDA en modo feria')
    return JsonResponse({'estado': 'OK'})


@csrf_exempt
def identificar(request):
    """1:N — Portón inteligente. Requiere sesión o modo feria (quiosco)."""
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    if _limitado(request, 'identificar', 40):
        return _err('Demasiados intentos, espera un minuto', 429)
    if not feria.activo() and not _sesion(request):
        return _err('Sesión requerida', 401)
    d = _json(request)
    if d is None:
        return _err('JSON inválido')
    v, e = _vector(d)
    if e:
        return e
    err = _exigir_vida(d, None, 'porton')
    if err:
        return err
    demo = feria.activo()
    try:
        usuario, mejor, _segundo = matching.identificar_1aN(v)
    except BiometriaKeyError as ex:
        return _err(str(ex), 500)
    if usuario:
        _log(usuario, 'acceso', 'ok', 'porton', mejor, demo=demo)
        return JsonResponse({'estado': 'OK', 'reconocido': True, 'nombre': usuario.nombre_completo,
                             'casa': usuario.casa.numero_casa if usuario.casa else '', 'score': round(mejor, 4)})
    vecino = Usuario.objects.filter(email__endswith=DEMO_DOMINIO).select_related('casa').order_by('id').first()
    notificados = 'Caseta de vigilancia'
    if vecino:
        notificados += f'; {vecino.nombre_completo} ({vecino.casa.numero_casa})'
    VisitaPendiente.objects.create(notificados=notificados, es_demo=demo)
    _log(None, 'acceso', 'denegado', 'porton', mejor, detalle='Visitante no registrado', demo=demo)
    _log(None, 'visita', 'pendiente', 'porton', detalle=f'Notificado: {notificados}', demo=demo)
    return JsonResponse({'estado': 'OK', 'reconocido': False, 'notificados': notificados,
                         'mensaje': 'Visitante no registrado'})


@csrf_exempt
def borrar(request):
    """Borrado definitivo de MI plantilla facial."""
    if request.method not in ('POST', 'DELETE'):
        return _err('Método no permitido', 405)
    s = _sesion(request)
    if not s:
        return _err('Sesión requerida', 401)
    n, _ = PlantillaFacial.objects.filter(usuario=s.usuario).delete()
    _log(s.usuario, 'borrado', 'ok' if n else 'denegado', 'perfil', detalle='plantilla eliminada' if n else 'no había')
    return JsonResponse({'estado': 'OK', 'borrada': bool(n)})


def bitacora(request):
    s = _sesion(request)
    if not s and not feria.activo():
        return _err('Sesión requerida', 401)
    try:
        limite = max(1, min(200, int(request.GET.get('limite', 30))))
    except ValueError:
        limite = 30
    qs = BitacoraAcceso.objects.all()
    if s and not es_admin(s.usuario):
        qs = qs.filter(usuario=s.usuario)          # un vecino solo ve lo suyo
    if request.GET.get('solo_accesos') == '1':
        qs = qs.filter(evento__in=['acceso', 'visita'])
    if request.GET.get('desde_id'):
        qs = qs.filter(id__gt=int(request.GET['desde_id'])) if request.GET['desde_id'].isdigit() else qs
    filas = [{
        'id': b.id, 'fecha': timezone.localtime(b.fecha).strftime('%Y-%m-%d %H:%M:%S'), 'nombre': b.nombre,
        'casa': b.casa, 'evento': b.evento, 'resultado': b.resultado, 'origen': b.origen, 'score': b.score,
        'detalle': b.detalle, 'es_demo': b.es_demo} for b in qs[:limite]]
    return JsonResponse({'items': filas})


# ── modo feria ───────────────────────────────────────────────────────
def feria_vecinos(request):
    if not feria.activo():
        return _err('Solo disponible en modo feria', 403)
    out = []
    for u in Usuario.objects.filter(email__endswith=DEMO_DOMINIO).select_related('casa').order_by('id'):
        out.append({'id': u.id, 'nombre': u.nombre_completo, 'casa': u.casa.numero_casa if u.casa else '',
                    'registrado': PlantillaFacial.objects.filter(usuario=u).exists()})
    return JsonResponse({'vecinos': out})


@csrf_exempt
def feria_registrar(request):
    """Registra en vivo la cara de un vecino de EJEMPLO (solo usuarios demo, solo en modo feria)."""
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    if not feria.activo():
        return _err('Solo disponible en modo feria', 403)
    d = _json(request)
    if d is None:
        return _err('JSON inválido')
    if d.get('consentimiento') is not True:
        return _err('Debes aceptar el aviso de privacidad antes de registrar un rostro', 400)
    try:
        u = Usuario.objects.select_related('casa').get(id=int(d.get('usuario_id')), email__endswith=DEMO_DOMINIO)
    except (Usuario.DoesNotExist, TypeError, ValueError):
        return _err('Vecino de ejemplo no encontrado', 404)
    v, e = _vector(d)
    if e:
        return e
    err = _exigir_vida(d, u, 'feria')
    if err:
        return err
    try:
        blob = cifrar_vector(v)
    except BiometriaKeyError as ex:
        return _err(str(ex), 500)
    PlantillaFacial.objects.update_or_create(usuario=u, defaults={'vector_cifrado': blob, 'dim': len(v), 'es_demo': True})
    _log(u, 'registro', 'ok', 'feria', detalle='demo; consentimiento aceptado', demo=True)
    return JsonResponse({'estado': 'OK', 'mensaje': f'Rostro de {u.nombre_completo} registrado (demo)'})


def borrar_demo_todo():
    """Elimina TODO lo marcado como demo: plantillas, visitas y bitácora."""
    a, _ = PlantillaFacial.objects.filter(es_demo=True).delete()
    b, _ = VisitaPendiente.objects.filter(es_demo=True).delete()
    c, _ = BitacoraAcceso.objects.filter(es_demo=True).delete()
    return {'plantillas': a, 'visitas': b, 'bitacora': c}


@csrf_exempt
def feria_borrar_demo(request):
    if request.method not in ('POST', 'DELETE'):
        return _err('Método no permitido', 405)
    if not feria.activo():
        return _err('Solo disponible en modo feria', 403)
    return JsonResponse({'estado': 'OK', 'borrado': borrar_demo_todo()})
