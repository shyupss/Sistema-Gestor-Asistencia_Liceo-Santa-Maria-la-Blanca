from django.urls import path
from . import views

urlpatterns = [
    path('', views.pagina_alertas, name="alertas")
]