"""
URLs principales del proyecto Centinela
"""

from django.urls import path, include
from centinela import views_ia

urlpatterns = [
    path('', include('auth_app.urls')),
    path('api/ia/chat/', views_ia.chat_ia),
    path('api/ia/extraer-reporte/', views_ia.extraer_reporte_ia),
    path('api/ia/analizar-foto/', views_ia.analizar_foto_ia),
    path('api/ia/asistente/', views_ia.asistente_ia),
]

