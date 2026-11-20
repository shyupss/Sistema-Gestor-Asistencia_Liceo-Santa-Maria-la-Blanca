from django.urls import path
from .views import alertas
from .views import configuracion

urlpatterns = [
    path('', alertas.pagina_alertas, name="alertas"),
    path('configuracion', configuracion.pagina_configuracion, name="alertas_configuracion"),
    path('<int:alerta_id>/revisar/', alertas.revisar_alerta, name="alerta_revisar"),
]