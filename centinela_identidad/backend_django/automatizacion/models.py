"""Automatización de la administración: bandeja inteligente, visitas QR, reglas, resumen y anomalías."""
from django.db import models


class Incidente(models.Model):
    """Incidente triado por Centinela. Un incidente puede agrupar varios reportes duplicados."""
    ESTADOS = [('abierto', 'abierto'), ('resuelto_auto', 'resuelto_auto'),
               ('revision_admin', 'revision_admin'), ('cerrado', 'cerrado')]
    sdri_id = models.IntegerField(null=True, blank=True, db_index=True)   # id del reporte original en el SDRI
    creado = models.DateTimeField(db_index=True)
    usuario = models.CharField(max_length=200, blank=True)
    descripcion = models.TextField()
    tipo = models.CharField(max_length=60, blank=True)
    categoria = models.CharField(max_length=20, blank=True)
    prioridad = models.CharField(max_length=10, default='Media')
    zona = models.CharField(max_length=40, blank=True)                    # zona del plano (norte, caseta, parque...)
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    responsable = models.CharField(max_length=20, blank=True)             # vigilancia | mantenimiento | comite
    confianza = models.IntegerField(default=0)                            # 0-100
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    contador = models.IntegerField(default=1)                             # reportes agrupados
    grupo = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='duplicados')
    motivo = models.TextField(blank=True)                                 # explicación en español de lo que decidió Centinela
    resuelto_en = models.DateTimeField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'auto_incidente'
        ordering = ['-creado', '-id']


class AccionAuto(models.Model):
    """'Resuelta por Centinela': cada acción automática, con minutos ahorrados. Con cadena de hash."""
    fecha = models.DateTimeField(db_index=True)
    tipo = models.CharField(max_length=30)       # incidente | duplicado | post | visita_qr | resumen | regla | anomalia
    detalle = models.TextField()
    minutos = models.FloatField(default=0)
    es_demo = models.BooleanField(default=False)
    hash_prev = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = 'auto_accion'
        ordering = ['-fecha', '-id']


class VisitaQR(models.Model):
    usuario = models.ForeignKey('auth_app.Usuario', on_delete=models.CASCADE, related_name='visitas_qr')
    visita_nombre = models.CharField(max_length=120)
    valido_desde = models.DateTimeField()
    valido_hasta = models.DateTimeField()
    token_hash = models.CharField(max_length=64, unique=True)   # sha256 del token; el token NO se guarda
    usado = models.BooleanField(default=False)
    usado_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'auto_visita_qr'
        ordering = ['-creado']


class Regla(models.Model):
    """Motor de reglas  SI <campo> <op> <valor> ENTONCES <acción>."""
    nombre = models.CharField(max_length=120)
    evento = models.CharField(max_length=30)      # incidente_nuevo | acceso_denegado | publicacion
    campo = models.CharField(max_length=40)       # prioridad, tipo, categoria, zona, descripcion, hora
    operador = models.CharField(max_length=12)    # igual | contiene | mayor | menor
    valor = models.CharField(max_length=120)
    accion = models.CharField(max_length=30)      # asignar | prioridad | revision_admin | notificar
    parametro = models.CharField(max_length=120, blank=True)
    activa = models.BooleanField(default=True)
    veces = models.IntegerField(default=0)

    class Meta:
        db_table = 'auto_regla'


class ResumenDiario(models.Model):
    fecha = models.DateField(db_index=True)
    texto = models.TextField()
    generado_por = models.CharField(max_length=30, default='plantilla')   # groq|gemini|claude|plantilla
    creado = models.DateTimeField(auto_now_add=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'auto_resumen'
        ordering = ['-fecha', '-id']


class Alerta(models.Model):
    fecha = models.DateTimeField(db_index=True)
    tipo = models.CharField(max_length=30)       # fallos_porton | fuera_de_horario | spam_reportes
    motivo = models.TextField()                  # explicación en español
    clave = models.CharField(max_length=80, db_index=True)   # evita alertas repetidas
    atendida = models.BooleanField(default=False)
    es_demo = models.BooleanField(default=False)

    class Meta:
        db_table = 'auto_alerta'
        ordering = ['-fecha']
