from django.contrib import admin
from .models import (
    Alerta,
    Cargo,
    ConfigNotificaciones,
    ConfiguracionAlerta,
    Cuenta,
    Estado,
    EstadoAlumno,
    EstadoNotificaRol,
    Funcionario,
    FuncionarioCurso,
    HistorialEstadoAlumno,
    Notificacion,
    NotificacionCurso,
    Permiso,
    Rol,
    RolPermiso,
)

admin.site.register(Cargo)
admin.site.register(Funcionario)
admin.site.register(Estado)
admin.site.register(ConfiguracionAlerta)
admin.site.register(Alerta)
admin.site.register(EstadoAlumno)
admin.site.register(HistorialEstadoAlumno)
admin.site.register(Rol)
admin.site.register(Permiso)
admin.site.register(RolPermiso)
admin.site.register(FuncionarioCurso)
admin.site.register(EstadoNotificaRol)
admin.site.register(Notificacion)
admin.site.register(NotificacionCurso)
admin.site.register(Cuenta)


@admin.register(ConfigNotificaciones)
class ConfigNotificacionesAdmin(admin.ModelAdmin):
    """Fila única (id=1): no se puede agregar otra ni borrarla."""

    def has_add_permission(self, request):
        return not ConfigNotificaciones.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
