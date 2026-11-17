from django.urls import path
from . import views

urlpatterns = [
    path('api/auto/incidentes/ingresar/', views.ingresar_incidente),
    path('api/auto/acciones/', views.registrar_accion_externa),
    path('api/auto/centro/', views.centro),
    path('api/auto/incidentes/<int:pk>/resolver/', views.resolver_incidente),
    path('api/auto/alertas/<int:pk>/atender/', views.atender_alerta),
    path('api/auto/integridad/', views.integridad),
    path('api/auto/visitas/', views.visitas),
    path('api/auto/visitas/validar/', views.validar_visita),
    path('api/auto/reglas/', views.reglas),
    path('api/auto/resumen/generar/', views.resumen_generar),
    path('api/auto/demo/sembrar/', views.demo_sembrar),
    path('api/auto/demo/borrar/', views.demo_borrar),
]
