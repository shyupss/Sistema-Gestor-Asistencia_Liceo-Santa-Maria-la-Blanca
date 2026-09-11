from django.contrib import admin
from .models import Cargo, Funcionario, Estado, ConfiguracionAlerta, Alerta, EstadoAlumno, HistorialEstadoAlumno

admin.site.register(Cargo)
admin.site.register(Funcionario)
admin.site.register(Estado)
admin.site.register(ConfiguracionAlerta)
admin.site.register(Alerta)
admin.site.register(EstadoAlumno)
admin.site.register(HistorialEstadoAlumno)