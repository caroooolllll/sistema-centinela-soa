"""
URLs principales del proyecto Centinela
"""

from django.urls import path, include
from centinela import views_ia
from centinela.asistente import views as asistente_views, config as asistente_config

asistente_config.verificar_keys()  # avisa en consola si falta alguna key
from centinela.asistente import feria as _feria
_feria.iniciar()
from biometria import startup as _bio_startup
_bio_startup.iniciar()

urlpatterns = [
    # Pipeline rápido del asistente (streaming + voz)
    path('api/ia/asistente/stream/', asistente_views.asistente_stream),
    path('api/ia/stt/', asistente_views.stt),
    path('api/ia/tts/', asistente_views.tts),
    path('api/ia/sos-aviso/', asistente_views.sos_aviso),
    path('api/ia/estado/', asistente_views.estado),
    path('', include('auth_app.urls')),
    path('', include('biometria.urls')),
    path('api/ia/chat/', views_ia.chat_ia),
    path('api/ia/extraer-reporte/', views_ia.extraer_reporte_ia),
    path('api/ia/analizar-foto/', views_ia.analizar_foto_ia),
    path('api/ia/asistente/', views_ia.asistente_ia),
]

