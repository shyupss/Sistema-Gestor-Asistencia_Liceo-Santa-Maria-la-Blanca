from django.contrib import admin
from .models import Tipos_Asistencia, Estados_Solicitud, Paso_Lista, Justificaciones, Asistencia_Alumnos


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


admin.site.register(Tipos_Asistencia, SoloLecturaAdmin)
admin.site.register(Estados_Solicitud, SoloLecturaAdmin)
admin.site.register(Paso_Lista)
admin.site.register(Justificaciones)
admin.site.register(Asistencia_Alumnos)
