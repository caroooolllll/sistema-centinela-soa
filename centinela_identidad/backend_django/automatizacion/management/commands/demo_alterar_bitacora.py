"""DEMO de integridad: altera a propósito un registro de la bitácora SIN recalcular su hash.
Luego, en el Centro de mando → «Verificar integridad», se ve en qué evento se rompe la cadena.
Uso: python manage.py demo_alterar_bitacora [--id N]   |   restaurar: python manage.py borrar_demo_auto"""
from django.core.management.base import BaseCommand

from biometria.models import BitacoraAcceso


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument('--id', type=int)

    def handle(self, *a, **o):
        qs = BitacoraAcceso.objects.filter(es_demo=True).order_by('id')
        b = qs.filter(id=o['id']).first() if o.get('id') else qs[qs.count() // 2] if qs.exists() else None
        if not b:
            return self.stdout.write("No hay bitácora demo: corre primero seed_demo_auto.")
        antes = (b.resultado, b.nombre)
        BitacoraAcceso.objects.filter(pk=b.pk).update(resultado='ok', nombre='Intruso (alterado)')   # sin tocar hash
        self.stdout.write(self.style.WARNING(f"Evento #{b.id} alterado a propósito: {antes} -> ('ok', 'Intruso (alterado)'). "
                                             "Ahora pulsa «Verificar integridad»."))
