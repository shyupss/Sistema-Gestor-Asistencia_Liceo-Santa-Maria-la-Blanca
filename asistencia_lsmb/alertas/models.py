from django.db import models


class Cargo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre


class Funcionario(models.Model):
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='funcionarios')
    rut = models.CharField(max_length=15, unique=True)
    nombre = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} - {self.rut}"


class Estado(models.Model):
    nombre = models.CharField(max_length=20, unique=True)
    umbral_minimo = models.DecimalField(max_digits=5, decimal_places=2)
    genera_alerta = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre


class ConfiguracionAlerta(models.Model):
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name='configuraciones')
    cargo = models.ForeignKey(Cargo, on_delete=models.CASCADE, related_name='configuraciones_alerta')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['estado', 'cargo'],
                name='uq_config_alerta_estado_cargo',
            )
        ]


class Alerta(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='alertas')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='alertas'
    )
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='alertas')
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='alertas')
    fecha = models.DateTimeField(auto_now_add=True)
    revisada = models.BooleanField(default=False)
    fecha_revision = models.DateTimeField(null=True, blank=True)


class EstadoAlumno(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='estados')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='estados_alumno'
    )
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='estados_alumno')
    porcentaje_asistencia = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'periodo'],
                name='uq_estado_alumno_periodo',
            )
        ]


class HistorialEstadoAlumno(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='historial_estados')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='historial_estados_alumno'
    )
    estado_nuevo = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='cambios_nuevos')
    estado_anterior = models.ForeignKey(
        Estado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cambios_anteriores',
    )
    fecha_cambio = models.DateTimeField(auto_now_add=True)