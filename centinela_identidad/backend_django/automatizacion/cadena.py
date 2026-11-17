"""Bitácora con cadena de hash: cada evento guarda el hash del anterior. Alterar o borrar uno rompe la cadena.
Hay una cadena por valor de `es_demo`, así borrar lo demo nunca rompe la cadena real.
Límite conocido: quitar el ÚLTIMO evento de la cadena no se detecta (no hay un siguiente que lo delate)."""
import hashlib
import json

GENESIS = '0' * 64


def _campos_bitacora(o):
    return {'id': o.id, 'fecha': o.fecha.isoformat(), 'usuario_id': o.usuario_id, 'nombre': o.nombre, 'casa': o.casa,
            'evento': o.evento, 'resultado': o.resultado, 'origen': o.origen, 'score': o.score, 'detalle': o.detalle,
            'es_demo': o.es_demo}


def _campos_accion(o):
    return {'id': o.id, 'fecha': o.fecha.isoformat(), 'tipo': o.tipo, 'detalle': o.detalle, 'minutos': o.minutos,
            'es_demo': o.es_demo}


def calcular(prev, campos):
    return hashlib.sha256((prev + json.dumps(campos, sort_keys=True, default=str, ensure_ascii=False)).encode()).hexdigest()


def sellar(obj, extraer):
    """Calcula hash_prev/hash de un registro recién creado (el id y la fecha ya existen)."""
    M = type(obj)
    ant = M.objects.filter(es_demo=obj.es_demo, id__lt=obj.id).order_by('-id').first()
    obj.hash_prev = ant.hash if ant and ant.hash else GENESIS
    obj.hash = calcular(obj.hash_prev, extraer(obj))
    M.objects.filter(pk=obj.pk).update(hash_prev=obj.hash_prev, hash=obj.hash)
    return obj


def sellar_bitacora(o):
    return sellar(o, _campos_bitacora)


def sellar_accion(o):
    return sellar(o, _campos_accion)


def verificar(modelo, extraer, es_demo):
    """→ {ok, total, roto_en_id, motivo}. Reporta el PRIMER evento donde se rompe la cadena."""
    prev, total = GENESIS, 0
    for o in modelo.objects.filter(es_demo=es_demo).order_by('id'):
        total += 1
        if not o.hash:
            continue                      # registros anteriores a la función (sin sellar)
        if o.hash_prev != prev and total > 1:
            return {'ok': False, 'total': total, 'roto_en_id': o.id,
                    'motivo': f'El evento #{o.id} apunta a un eslabón anterior que ya no coincide: se alteró o se borró un evento previo.'}
        if calcular(o.hash_prev, extraer(o)) != o.hash:
            return {'ok': False, 'total': total, 'roto_en_id': o.id,
                    'motivo': f'El contenido del evento #{o.id} fue modificado después de registrarse.'}
        prev = o.hash
    return {'ok': True, 'total': total, 'roto_en_id': None, 'motivo': 'Cadena íntegra'}
