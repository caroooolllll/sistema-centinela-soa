"""Biometría facial: solo se guarda el VECTOR de características, cifrado. Nunca la foto."""
from django.db import models


class PlantillaFacial(models.Model):
    usuario = models.OneToOneField('auth_app.Usuario', on_delete=models.CASCADE, related_name='plantilla_facial')
    vector_cifrado = models.BinaryField()          # Fernet(float32[dim] normalizado)
    dim = models.IntegerField()
    creado = models.DateTimeField(auto_now_add=True)
    es_demo = models.BooleanField(default=False)   # registrada en modo feria

    class Meta:
        db_table = 'biometria_plantilla'


class BitacoraAcceso(models.Model):
    EVENTOS = [('registro', 'registro'), ('verificacion', 'verificacion'), ('acceso', 'acceso'),
               ('borrado', 'borrado'), ('visita', 'visita')]
    RESULTADOS = [('ok', 'ok'), ('denegado', 'denegado'), ('pendiente', 'pendiente')]

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey('auth_app.Usuario', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='bitacora_acceso')
    nombre = models.CharField(max_length=200, blank=True)   # copia legible (sigue ahí si se borra el usuario)
    casa = models.CharField(max_length=20, blank=True)
    evento = models.CharField(max_length=20, choices=EVENTOS)
    resultado = models.CharField(max_length=20, choices=RESULTADOS)
    origen = models.CharField(max_length=30)                 # perfil | login | accion_critica | porton | feria
    score = models.FloatField(null=True, blank=True)
    detalle = models.TextField(blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'biometria_bitacora'
        ordering = ['-fecha', '-id']


class VisitaPendiente(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, default='pendiente')   # pendiente | atendida
    notificados = models.TextField(blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'biometria_visita'
        ordering = ['-fecha', '-id']
