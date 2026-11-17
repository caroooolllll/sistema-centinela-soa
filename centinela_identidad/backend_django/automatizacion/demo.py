"""Datos FICTICIOS de 2–3 semanas para que el Centro de mando se vea vivo. Todo marcado es_demo y borrable."""
import random
from datetime import timedelta

from django.utils import timezone

from biometria.models import BitacoraAcceso, VisitaPendiente
from . import cadena, servicios
from .models import AccionAuto, Alerta, Incidente, ResumenDiario, VisitaQR

PLANTILLAS = [   # (tipo, categoria, prioridad, zona-hint, descripciones)
    ('Robo', 'seguridad', 'Media', 'Caseta', ['Robaron una bicicleta cerca de la caseta anoche', 'Se llevaron paquetes de la entrada principal']),
    ('Persona sospechosa', 'seguridad', 'Media', 'Calle norte', ['Persona desconocida merodeando en la calle norte', 'Un sujeto extraño observa las casas de la calle norte']),
    ('Vandalismo', 'seguridad', 'Media', 'Parque', ['Pintaron grafiti en los juegos del parque', 'Rompieron una banca del parque']),
    ('Ruido excesivo', 'seguridad', 'Baja', 'Alberca', ['Fiesta con música muy fuerte en el salón del club', 'Ruido y gritos en la alberca de noche']),
    ('Fuga de agua', 'ambiental', 'Media', 'Calle sur', ['Fuga de agua en la tubería de la calle sur', 'Hay una fuga que inunda la calle sur']),
    ('Alumbrado desperdiciando energía', 'ambiental', 'Baja', 'Estacionamiento', ['Lámparas prendidas de día en el estacionamiento', 'Poste de luz parpadea en el estacionamiento']),
    ('Árbol caído o dañado', 'ambiental', 'Media', 'Parque', ['Una rama grande cayó en el parque', 'Árbol caído bloquea el paso en el parque']),
    ('Tiradero clandestino', 'ambiental', 'Baja', 'Calle norte', ['Dejaron basura y escombro en la calle norte']),
    ('Otro', 'seguridad', 'Baja', '', ['Algo raro pasó, no sé bien qué', 'Quiero avisar de un asunto']),
]
NOMBRES = ['Ana Torres (demo)', 'Luis Herrera (demo)', 'Sofía Mendoza (demo)']


def sembrar(dias=18, semilla=42):
    r = random.Random(semilla)
    borrar()
    ahora = timezone.now()
    n_inc = 0
    for d in range(dias, 0, -1):
        for _ in range(r.randint(2, 5)):
            tipo, cat, pri, zona, descs = r.choice(PLANTILLAS)
            t = (ahora - timedelta(days=d)).replace(hour=r.choice([7, 9, 13, 18, 19, 20, 21, 22, 23, 2]), minute=r.randint(0, 59))
            servicios.triar_incidente(descripcion=r.choice(descs), tipo=tipo, categoria=cat, prioridad=pri, usuario=r.choice(NOMBRES),
                                      creado=t, demo=True)
            n_inc += 1
            if r.random() < 0.18:   # un vecino más reporta lo mismo → duplicado
                servicios.triar_incidente(descripcion=r.choice(descs), tipo=tipo, categoria=cat, prioridad=pri,
                                          usuario=r.choice(NOMBRES), creado=t + timedelta(minutes=r.randint(5, 90)), demo=True)
                n_inc += 1
    # los dudosos pasaron por el admin: la mayoría ya los cerró (tardó entre 20 min y 4 h); los más nuevos siguen pendientes
    for i in Incidente.objects.filter(es_demo=True, estado='revision_admin', creado__lt=ahora - timedelta(days=1)):
        if r.random() < 0.7:
            Incidente.objects.filter(pk=i.pk).update(estado='cerrado', resuelto_en=i.creado + timedelta(minutes=r.randint(20, 240)))
    # accesos del portón y visitas
    for d in range(dias, -1, -1):
        for _ in range(r.randint(3, 8)):
            t = (ahora - timedelta(days=d)).replace(hour=r.choice([7, 8, 14, 18, 19, 21]), minute=r.randint(0, 59), second=r.randint(0, 59))
            if t > ahora:
                t = ahora - timedelta(minutes=r.randint(1, 600))
            ok = r.random() < 0.8
            nombre = r.choice(NOMBRES) if ok else ''
            b = BitacoraAcceso.objects.create(usuario=None, nombre=nombre, casa='Casa 2%d' % r.randint(1, 3) if ok else '', evento='acceso',
                                              resultado='ok' if ok else 'denegado', origen='porton', score=round(r.uniform(.91, .99), 4) if ok else None,
                                              detalle='' if ok else 'Visitante no registrado', es_demo=True)
            BitacoraAcceso.objects.filter(pk=b.pk).update(fecha=t)
            b.refresh_from_db()
            cadena.sellar_bitacora(b)
            if not ok:
                vp = VisitaPendiente.objects.create(notificados='Caseta de vigilancia', estado='atendida', es_demo=True)
                VisitaPendiente.objects.filter(pk=vp.pk).update(fecha=t)
        for _ in range(r.randint(0, 3)):    # visitas con QR
            servicios.registrar_accion('visita_qr', f'Visita «Invitado {r.randint(1, 99)}» entró con QR', True,
                                       fecha=(ahora - timedelta(days=d)).replace(hour=r.choice([12, 17, 20])))
        for _ in range(r.randint(2, 7)):    # publicaciones moderadas automáticamente
            servicios.registrar_accion('post', 'Publicación moderada automáticamente', True,
                                       fecha=(ahora - timedelta(days=d)).replace(hour=r.choice([9, 11, 16, 19])))
    # resúmenes diarios de ejemplo
    for d in (3, 2, 1):
        ResumenDiario.objects.create(fecha=(ahora - timedelta(days=d)).date(), generado_por='plantilla', es_demo=True,
                                     texto=servicios._plantilla_resumen(servicios.hechos_del_dia(ahora - timedelta(days=d + 1), demo=True)))
        servicios.registrar_accion('resumen', 'Resumen diario generado (plantilla)', True, fecha=ahora - timedelta(days=d))
    servicios.detectar_anomalias(demo=True)
    return {'incidentes': n_inc, 'acciones': AccionAuto.objects.filter(es_demo=True).count(),
            'accesos': BitacoraAcceso.objects.filter(es_demo=True).count(), 'alertas': Alerta.objects.filter(es_demo=True).count()}


def borrar():
    out = {}
    for M in (Incidente, AccionAuto, VisitaQR, ResumenDiario, Alerta, BitacoraAcceso, VisitaPendiente):
        out[M.__name__] = M.objects.filter(es_demo=True).delete()[0]
    from .models import Regla  # las reglas no son datos de demo: se conservan
    return out
