from django.contrib import admin
from .models import PeriodoAcademico, Curso, Alumno, Apoderado, EstadoMatricula, Matricula

admin.site.register(PeriodoAcademico)
admin.site.register(Curso)
admin.site.register(Alumno)
admin.site.register(Apoderado)
admin.site.register(EstadoMatricula)
admin.site.register(Matricula)