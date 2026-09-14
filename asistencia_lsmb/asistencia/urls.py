from django.urls import path
from asistencia.views.asistencia_cursos import pagina_asistencia
from asistencia.views.asistencia_registro import pagina_registrar_asistencia
from asistencia.views.justificaciones import pagina_justificaciones

urlpatterns = [
    path("", pagina_asistencia, name="asistencia"),
    path("registrar/", pagina_registrar_asistencia, name="registrar_asistencia"),
    path("justificaciones/", pagina_justificaciones, name="justificaciones")
]