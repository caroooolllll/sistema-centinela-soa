"""Borra TODO lo marcado como demo (plantillas, visitas y bitácora). Uso: python manage.py borrar_demo"""
from django.core.management.base import BaseCommand

from biometria.views import borrar_demo_todo


class Command(BaseCommand):
    help = "Borra todos los registros biométricos de demo"

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f"Borrado: {borrar_demo_todo()}"))
