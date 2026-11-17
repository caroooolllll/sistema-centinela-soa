"""Tarea programada: genera el resumen diario a la hora configurada (AUTO_RESUMEN_HORA, default 20:00)."""
import os
import threading
import time


def _loop():
    from django.utils import timezone
    ultimo = None
    while True:
        try:
            ahora = timezone.localtime()
            hora = int(os.getenv('AUTO_RESUMEN_HORA', '20'))
            if ahora.hour == hora and ultimo != ahora.date():
                from . import servicios
                from .models import ResumenDiario
                if not ResumenDiario.objects.filter(fecha=ahora.date(), es_demo=False).exists():
                    servicios.generar_resumen()
                ultimo = ahora.date()
        except Exception:
            pass
        time.sleep(60)


def iniciar():
    if os.getenv('AUTO_RESUMEN_PROGRAMADO', 'true').lower() in ('1', 'true', 'si') and os.getenv('RUN_MAIN') != 'false':
        threading.Thread(target=_loop, daemon=True).start()
