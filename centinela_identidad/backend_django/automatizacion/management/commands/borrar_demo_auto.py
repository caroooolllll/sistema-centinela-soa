"""Borra TODOS los datos de demo de la automatización. Uso: python manage.py borrar_demo_auto"""
from django.core.management.base import BaseCommand

from automatizacion.demo import borrar


class Command(BaseCommand):
    def handle(self, *a, **o):
        self.stdout.write(self.style.SUCCESS(f"Borrado: {borrar()}"))
