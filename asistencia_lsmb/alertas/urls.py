from django.urls import path
from . import views

urlpatterns = [
    path('', views.pagina_alertas, name="alertas"),
    path('<int:alerta_id>/revisar/', views.revisar_alerta, name="alerta_revisar"),
]