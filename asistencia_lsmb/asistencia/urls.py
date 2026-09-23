from django.urls import path
from asistencia.views.asistencia_cursos import pagina_asistencia
from asistencia.views.asistencia_registro import pagina_registrar_asistencia
from asistencia.views.justificaciones import pagina_justificaciones
from asistencia.views.justificaciones_formulario import pagina_justificaciones_formulario
from asistencia.views.justificaciones_ficha import pagina_justificaciones_ficha

urlpatterns = [
    path("", pagina_asistencia, name="asistencia"),
    path("registrar/", pagina_registrar_asistencia, name="registrar_asistencia"),
    path("justificaciones/", pagina_justificaciones, name="justificaciones"),
    path("justificaciones/registro", pagina_justificaciones_formulario, name="justificaciones_formulario"),
    path("justificaciones/ficha", pagina_justificaciones_ficha, name="justificaciones_ficha"),
]