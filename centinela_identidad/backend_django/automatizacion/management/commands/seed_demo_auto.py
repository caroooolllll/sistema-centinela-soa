"""Siembra 2-3 semanas de datos ficticios (todo marcado demo). Uso: python manage.py seed_demo_auto"""
from django.core.management.base import BaseCommand

from automatizacion.demo import sembrar


class Command(BaseCommand):
    help = "Datos de demo para el Centro de mando"

    def handle(self, *a, **o):
        self.stdout.write(self.style.SUCCESS(f"Sembrado: {sembrar()}"))
