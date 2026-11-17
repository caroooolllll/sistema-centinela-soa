"""Genera el resumen diario ahora (también lo hace solo a las 20:00). Uso: python manage.py resumen_diario"""
from django.core.management.base import BaseCommand

from automatizacion.servicios import generar_resumen


class Command(BaseCommand):
    def handle(self, *a, **o):
        r = generar_resumen()
        self.stdout.write(f"[{r.generado_por}] {r.texto}")
