from django.db import models
import uuid


class CargaDatos(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("procesando", "Procesando"),
        ("completada", "Completada"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.CharField(max_length=20)
    registros = models.JSONField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    total = models.PositiveIntegerField(default=0)
    progreso_actual = models.PositiveIntegerField(default=0)
    progreso_porcentaje = models.PositiveIntegerField(default=0)
    etapa = models.CharField(max_length=20, default="preparando")
    mensaje_progreso = models.CharField(max_length=200, blank=True)
    resultado = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
