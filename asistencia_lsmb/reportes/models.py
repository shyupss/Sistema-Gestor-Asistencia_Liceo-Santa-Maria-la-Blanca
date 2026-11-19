from django.db import models
from django.utils import timezone


class ReporteGenerado(models.Model):
    TIPOS = (
        ("planilla", "Planilla de asistencia"),
        ("mensual", "Reporte mensual"),
        ("semestral", "Semestral y anual"),
        ("alumno", "Ficha por alumno"),
        ("criticos", "Atención y críticos"),
        ("justificaciones", "Justificaciones y retiros"),
    )
    ESTADOS = (
        ("pendiente", "Pendiente"),
        ("generando", "Generando"),
        ("completado", "Completado"),
        ("error", "Error"),
    )

    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    periodo = models.ForeignKey(
        "academico.PeriodoAcademico",
        on_delete=models.PROTECT,
        related_name="reportes_generados",
    )
    semestre = models.CharField(
        max_length=1,
        choices=(("1", "Semestre 1"), ("2", "Semestre 2")),
    )
    cursos_ids = models.JSONField(default=list)
    filtros = models.JSONField(default=dict)
    generado_por = models.ForeignKey(
        "alertas.Funcionario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reportes_generados",
    )
    archivo = models.FileField(upload_to="reportes/", blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-creado_en",)

    def __str__(self):
        return self.nombre
