from django.db import models
from academico.models import Alumno, Curso


class Tipos_Asistencia(models.Model):
    nombre = models.CharField(max_length=20, unique=True)
    cuenta_como_ausencia = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre

class Estados_Solicitud(models.Model):
    nombre = models.CharField(max_length=20, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    es_estado_final = models.BooleanField(default=False)
    cubre_ausencia = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre


class Paso_Lista(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE)
    funcionario = models.ForeignKey(
        'alertas.Funcionario', on_delete=models.PROTECT, related_name='pasos_lista'
    )
    jornada = models.CharField(max_length=20, default='unica')
    fecha = models.DateField()
    hora_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['curso', 'fecha', 'jornada'],
                name='uq_paso_lista_curso_fecha_jornada',
            )
        ]


class Justificaciones(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    funcionario_resuelve = models.ForeignKey(
        'alertas.Funcionario',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='justificaciones_resueltas',
    )
    estado_solicitud = models.ForeignKey(Estados_Solicitud, on_delete=models.PROTECT)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    motivo = models.TextField(blank=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)


class Asistencia_Alumnos(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    paso_lista = models.ForeignKey(Paso_Lista, on_delete=models.CASCADE)
    tipo_asistencia = models.ForeignKey(Tipos_Asistencia, on_delete=models.CASCADE)
    justificacion = models.ForeignKey(
        Justificaciones,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asistencias',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['paso_lista', 'alumno'],
                name='uq_asistencia_paso_lista_alumno',
            )
        ]