from django.urls import path
from . import views

urlpatterns = [
    path('api/biometria/config/', views.config),
    path('api/biometria/estado/', views.estado),
    path('api/biometria/registrar/', views.registrar),
    path('api/biometria/verificar/', views.verificar),
    path('api/biometria/omitir/', views.omitir),
    path('api/biometria/identificar/', views.identificar),
    path('api/biometria/borrar/', views.borrar),
    path('api/biometria/bitacora/', views.bitacora),
    path('api/biometria/feria/vecinos/', views.feria_vecinos),
    path('api/biometria/feria/registrar/', views.feria_registrar),
    path('api/biometria/feria/borrar-demo/', views.feria_borrar_demo),
]
