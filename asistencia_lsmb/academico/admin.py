from django.contrib import admin
from .models import PeriodoAcademico, Curso, Alumno, Apoderado, EstadoMatricula, Matricula, AlumnoApoderado


class SoloLecturaAdmin(admin.ModelAdmin):
    """Catálogo fijo: se puede ver, pero no agregar, modificar ni borrar."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


admin.site.register(PeriodoAcademico)
admin.site.register(Curso)
admin.site.register(Alumno)
admin.site.register(Apoderado)
admin.site.register(AlumnoApoderado)
admin.site.register(EstadoMatricula, SoloLecturaAdmin)
admin.site.register(Matricula)