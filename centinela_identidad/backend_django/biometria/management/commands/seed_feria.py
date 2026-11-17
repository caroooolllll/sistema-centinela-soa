"""Crea 3 vecinos de ejemplo (datos ficticios, SIN biometría) para la demo de la feria.
Uso: python manage.py seed_feria"""
import hashlib

from django.core.management.base import BaseCommand

from auth_app.models import PadronCasas, Usuario

EJEMPLOS = [
    ("Ana Torres (demo)", "Casa 21", 38, "ana@demo.centinela.local"),
    ("Luis Herrera (demo)", "Casa 22", 52, "luis@demo.centinela.local"),
    ("Sofía Mendoza (demo)", "Casa 23", 29, "sofia@demo.centinela.local"),
]


class Command(BaseCommand):
    help = "Crea 3 vecinos de ejemplo ficticios para la feria (contraseña: demo1234)"

    def handle(self, *args, **opts):
        pw = hashlib.sha256(b"demo1234").hexdigest()
        for nombre, casa_n, edad, email in EJEMPLOS:
            casa, _ = PadronCasas.objects.get_or_create(numero_casa=casa_n, defaults={"ocupada": False})
            u, creado = Usuario.objects.get_or_create(
                email=email, defaults={"nombre_completo": nombre, "casa": casa, "edad": edad, "password": pw})
            if creado:
                casa.ocupada = True
                casa.save()
            self.stdout.write(f"{'creado ' if creado else 'ya existía'}: {nombre} — {casa_n} — {email}")
        self.stdout.write(self.style.SUCCESS("Listo. Contraseña de los vecinos demo: demo1234. Sin biometría: se registran en vivo."))
