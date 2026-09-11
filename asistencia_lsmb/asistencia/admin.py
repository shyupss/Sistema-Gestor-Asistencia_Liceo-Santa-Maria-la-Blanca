from django.contrib import admin
from .models import Tipos_Asistencia, Estados_Solicitud, Paso_Lista, Justificaciones, Asistencia_Alumnos

admin.site.register(Tipos_Asistencia)
admin.site.register(Estados_Solicitud)
admin.site.register(Paso_Lista)
admin.site.register(Justificaciones)
admin.site.register(Asistencia_Alumnos)