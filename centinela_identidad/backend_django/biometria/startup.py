"""Se ejecuta al cargar las URLs: avisa si falta la llave y, en modo feria, borra los datos demo al cerrar."""
import atexit

from centinela.asistente import feria
from .crypto import avisar_si_falta_key


def _borrar_demo_al_cerrar():
    try:
        from .views import borrar_demo_todo
        r = borrar_demo_todo()
        print(f"[FERIA] Cierre: datos demo borrados {r}", flush=True)
    except Exception as e:  # la base puede no estar disponible al cerrar
        print(f"[FERIA] No se pudieron borrar los datos demo al cerrar ({type(e).__name__}). "
              f"Usa el botón 'Borrar datos demo' o: python manage.py borrar_demo", flush=True)


def iniciar():
    avisar_si_falta_key()
    if feria.activo():
        atexit.register(_borrar_demo_al_cerrar)
