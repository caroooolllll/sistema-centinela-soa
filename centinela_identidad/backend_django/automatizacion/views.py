"""API del Centro de mando y de la automatización. Admin = admin@centinela.com (como en el resto del sistema)."""
import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from biometria import views as bio
from biometria.models import BitacoraAcceso, VisitaPendiente
from centinela.asistente import feria

from . import cadena, servicios
from .models import AccionAuto, Alerta, Incidente, Regla, ResumenDiario, VisitaQR


def _json(request):
    try:
        d = json.loads(request.body or b'{}')
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _err(msg, status=400):
    return JsonResponse({'estado': 'ERROR', 'mensaje': msg}, status=status)


def _admin_o_feria(request):
    s = bio._sesion(request)
    return (s and bio.es_admin(s.usuario)) or feria.activo()


def _solo_local(request):
    return request.META.get('REMOTE_ADDR') in ('127.0.0.1', '::1')


def _fila_inc(i):
    return {'id': i.id, 'fecha': timezone.localtime(i.creado).strftime('%Y-%m-%d %H:%M'), 'tipo': i.tipo, 'prioridad': i.prioridad,
            'zona': i.zona, 'responsable': i.responsable, 'confianza': i.confianza, 'estado': i.estado, 'contador': i.contador,
            'descripcion': i.descripcion[:160], 'motivo': i.motivo, 'es_demo': i.es_demo}


# ── ingesta desde los otros servicios (solo desde esta misma máquina) ─────────
@csrf_exempt
def ingresar_incidente(request):
    if request.method != 'POST' or not _solo_local(request):
        return _err('No permitido', 403)
    d = _json(request)
    if not str(d.get('descripcion', '')).strip():
        return _err('descripcion requerida')
    lat = d.get('latitud')
    try:
        lat, lon = (float(lat), float(d.get('longitud'))) if lat not in (None, '') else (None, None)
    except (TypeError, ValueError):
        lat = lon = None
    inc = servicios.triar_incidente(descripcion=str(d['descripcion']), tipo=str(d.get('tipo') or 'Otro'),
                                    categoria=str(d.get('categoria') or 'seguridad'), prioridad=str(d.get('prioridad') or 'Media'),
                                    usuario=str(d.get('usuario') or ''), sdri_id=d.get('sdri_id'), latitud=lat, longitud=lon)
    return JsonResponse({'estado': 'OK', 'incidente': _fila_inc(inc)})


@csrf_exempt
def registrar_accion_externa(request):
    """Moderación automática (Flask) y otros servicios anotan lo que resolvieron solos."""
    if request.method != 'POST' or not _solo_local(request):
        return _err('No permitido', 403)
    d = _json(request)
    tipo = d.get('tipo')
    if tipo not in servicios.MINUTOS:
        return _err('tipo inválido')
    servicios.registrar_accion(tipo, str(d.get('detalle', ''))[:300])
    return JsonResponse({'estado': 'OK'})


# ── Centro de mando ───────────────────────────────────────────────────
def centro(request):
    if not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    demo = request.GET.get('demo') == '1'
    servicios.detectar_anomalias(demo=demo)
    res = ResumenDiario.objects.filter(es_demo=demo).first()
    return JsonResponse({
        'kpis': servicios.kpis(demo),
        'pendientes': [_fila_inc(i) for i in Incidente.objects.filter(estado='revision_admin', es_demo=demo, grupo__isnull=True)[:20]],
        'alertas': [{'id': a.id, 'fecha': timezone.localtime(a.fecha).strftime('%Y-%m-%d %H:%M'), 'tipo': a.tipo, 'motivo': a.motivo}
                    for a in Alerta.objects.filter(atendida=False, es_demo=demo)[:10]],
        'acciones': [{'fecha': timezone.localtime(a.fecha).strftime('%m-%d %H:%M'), 'tipo': a.tipo, 'detalle': a.detalle, 'minutos': a.minutos}
                     for a in AccionAuto.objects.filter(es_demo=demo)[:12]],
        'accesos': [{'id': b.id, 'fecha': timezone.localtime(b.fecha).strftime('%H:%M:%S'), 'nombre': b.nombre or 'Visitante',
                     'casa': b.casa, 'resultado': b.resultado, 'origen': b.origen}
                    for b in BitacoraAcceso.objects.filter(evento='acceso', es_demo=demo)[:10]],
        'mapa': servicios.mapa_calor(demo),
        'resumen': {'texto': res.texto, 'por': res.generado_por, 'fecha': str(res.fecha)} if res else None,
        'demo': demo,
    })


@csrf_exempt
def resolver_incidente(request, pk):
    s = bio._sesion(request)
    if request.method != 'POST' or not ((s and bio.es_admin(s.usuario)) or feria.activo()):
        return _err('Solo el administrador', 403)
    try:
        i = Incidente.objects.get(pk=pk)
    except Incidente.DoesNotExist:
        return _err('No existe', 404)
    i.estado, i.resuelto_en = 'cerrado', timezone.now()
    i.motivo += ' | Cerrado por el administrador.'
    i.save()
    return JsonResponse({'estado': 'OK'})


@csrf_exempt
def atender_alerta(request, pk):
    if request.method != 'POST' or not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    Alerta.objects.filter(pk=pk).update(atendida=True)
    return JsonResponse({'estado': 'OK'})


def integridad(request):
    if not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    out = {}
    for demo in (False, True):
        out['demo' if demo else 'real'] = {
            'bitacora_accesos': cadena.verificar(BitacoraAcceso, cadena._campos_bitacora, demo),
            'acciones_automaticas': cadena.verificar(AccionAuto, cadena._campos_accion, demo)}
    out['ok'] = all(v['ok'] for g in ('real', 'demo') for v in out[g].values())
    return JsonResponse(out)


# ── Visitas con QR ──────────────────────────────────────────────────────
@csrf_exempt
def visitas(request):
    s = bio._sesion(request)
    if not s:
        return _err('Sesión requerida', 401)
    if request.method == 'GET':
        return JsonResponse({'items': [{
            'id': v.id, 'nombre': v.visita_nombre, 'desde': timezone.localtime(v.valido_desde).strftime('%Y-%m-%d %H:%M'),
            'hasta': timezone.localtime(v.valido_hasta).strftime('%Y-%m-%d %H:%M'), 'usado': v.usado,
            'vencida': (not v.usado) and v.valido_hasta < timezone.now()} for v in VisitaQR.objects.filter(usuario=s.usuario)[:30]]})
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    d = _json(request)
    nombre = str(d.get('nombre', '')).strip()
    if not nombre:
        return _err('Escribe el nombre de tu visita')
    try:
        desde = timezone.make_aware(datetime.strptime(f"{d.get('fecha')} {d.get('hora')}", '%Y-%m-%d %H:%M'))
        dur = int(d.get('duracion_min') or 240)
    except (ValueError, TypeError):
        return _err('Fecha u hora inválidas (usa AAAA-MM-DD y HH:MM)')
    v, qr = servicios.crear_visita(s.usuario, nombre, desde, dur, demo=bio.es_demo_usuario(s.usuario))
    return JsonResponse({'estado': 'OK', 'id': v.id, 'qr': qr,
                         'valido_hasta': timezone.localtime(v.valido_hasta).strftime('%Y-%m-%d %H:%M')})


@csrf_exempt
def validar_visita(request):
    """Lo llama el Portón al leer un QR. Concedido o negado → bitácora. Sin intervención del admin."""
    if request.method != 'POST':
        return _err('Método no permitido', 405)
    if not feria.activo() and not bio._sesion(request):
        return _err('Sesión requerida', 401)
    qr = str(_json(request).get('qr', ''))[:200]
    demo = feria.activo()
    ok, motivo, v = servicios.validar_qr(qr, demo)
    quien = f'Visita: {v.visita_nombre}' if v else 'QR desconocido'
    casa = v.usuario.casa.numero_casa if v and v.usuario.casa else ''
    b = BitacoraAcceso.objects.create(
        usuario=None, nombre=quien, casa=casa, evento='acceso', resultado='ok' if ok else 'denegado', origen='porton_qr',
        detalle=(motivo + (f' · invitó {v.usuario.nombre_completo}' if v else ''))[:300], es_demo=bool(demo or (v and v.es_demo)))
    cadena.sellar_bitacora(b)
    servicios.al_registrar_acceso(b)
    if ok:
        servicios.registrar_accion('visita_qr', f'Visita «{v.visita_nombre}» entró con QR (invitó {v.usuario.nombre_completo})', b.es_demo)
    return JsonResponse({'estado': 'OK', 'concedido': ok, 'motivo': motivo,
                         'visita': v.visita_nombre if v else None, 'casa': casa})


# ── Reglas ───────────────────────────────────────────────────────────────
def _fila_regla(r):
    return {'id': r.id, 'nombre': r.nombre, 'evento': r.evento, 'campo': r.campo, 'operador': r.operador, 'valor': r.valor,
            'accion': r.accion, 'parametro': r.parametro, 'activa': r.activa, 'veces': r.veces}


ACCIONES_PERMITIDAS = {'asignar', 'prioridad', 'revision_admin', 'notificar'}   # nunca abrir portón / borrar / SOS


@csrf_exempt
def reglas(request):
    s = bio._sesion(request)
    admin = s and bio.es_admin(s.usuario)
    if request.method == 'GET':
        if not (admin or feria.activo()):
            return _err('Solo el administrador', 403)
        servicios.asegurar_reglas()
        return JsonResponse({'items': [_fila_regla(r) for r in Regla.objects.all().order_by('id')]})
    if request.method != 'POST' or not admin:
        return _err('Solo el administrador', 403)
    d = _json(request)
    if d.get('id'):                                   # activar/desactivar o borrar
        r = Regla.objects.filter(pk=d['id']).first()
        if not r:
            return _err('No existe', 404)
        if d.get('borrar'):
            r.delete()
        else:
            r.activa = bool(d.get('activa', r.activa))
            r.save()
        return JsonResponse({'estado': 'OK'})
    if d.get('accion') not in ACCIONES_PERMITIDAS:
        return _err('Acción no permitida. Las reglas solo pueden: ' + ', '.join(sorted(ACCIONES_PERMITIDAS)))
    if d.get('evento') not in ('incidente_nuevo', 'acceso_denegado') or d.get('operador') not in ('igual', 'contiene', 'mayor', 'menor'):
        return _err('Evento u operador inválido')
    r = Regla.objects.create(nombre=str(d.get('nombre') or 'Regla')[:120], evento=d['evento'], campo=str(d.get('campo', ''))[:40],
                             operador=d['operador'], valor=str(d.get('valor', ''))[:120], accion=d['accion'],
                             parametro=str(d.get('parametro', ''))[:120])
    return JsonResponse({'estado': 'OK', 'regla': _fila_regla(r)})


# ── Resumen diario ────────────────────────────────────────────────────────
@csrf_exempt
def resumen_generar(request):
    if request.method != 'POST' or not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    r = servicios.generar_resumen(demo=bool(_json(request).get('demo')))
    return JsonResponse({'estado': 'OK', 'texto': r.texto, 'por': r.generado_por})


# ── Datos de demo ─────────────────────────────────────────────────────────
@csrf_exempt
def demo_sembrar(request):
    if request.method != 'POST' or not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    from .demo import sembrar
    return JsonResponse({'estado': 'OK', 'creado': sembrar()})


@csrf_exempt
def demo_borrar(request):
    if request.method != 'POST' or not _admin_o_feria(request):
        return _err('Solo el administrador', 403)
    from .demo import borrar
    return JsonResponse({'estado': 'OK', 'borrado': borrar()})
