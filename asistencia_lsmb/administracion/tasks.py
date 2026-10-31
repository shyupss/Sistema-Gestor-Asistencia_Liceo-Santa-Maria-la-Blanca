from celery import Task, shared_task
from django.db import transaction

from .models import CargaDatos
from .services.carga_archivos import (
    ArchivoCargaError,
    cargar_asistencia,
    cargar_matriculas,
)


class CargaDatosTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        CargaDatos.objects.filter(pk=kwargs.get("carga_id") or args[0]).update(
            estado="error",
            error="Ocurrió un error inesperado durante la carga.",
        )


@shared_task(bind=True, base=CargaDatosTask)
def procesar_carga_datos(self, carga_id):
    carga = CargaDatos.objects.get(pk=carga_id)
    registros = carga.registros
    total = max(carga.total, 1)

    carga.estado = "procesando"
    carga.error = ""
    carga.progreso_actual = 0
    carga.progreso_porcentaje = 0
    carga.etapa = "preparando"
    carga.mensaje_progreso = "Preparando la carga y validando los registros..."
    carga.save(update_fields=[
        "estado",
        "error",
        "progreso_actual",
        "progreso_porcentaje",
        "etapa",
        "mensaje_progreso",
        "actualizado_en",
    ])
    ultimo_progreso_reportado = -1
    ultimo_porcentaje_reportado = -1
    self.update_state(
        state="PROGRESS",
        meta={
            "current": 0,
            "total": total,
            "percent": 0,
            "phase": "preparando",
            "message": "Preparando la carga y validando los registros...",
        },
    )

    def actualizar_progreso(phase, message, current):
        nonlocal ultimo_porcentaje_reportado, ultimo_progreso_reportado
        if phase == "validando":
            porcentaje = round(current * 50 / total)
        else:
            porcentaje = 50 + round(current * 50 / total)
        if (
            current != total
            and current - ultimo_progreso_reportado < 100
            and porcentaje == ultimo_porcentaje_reportado
        ):
            return
        ultimo_progreso_reportado = current
        ultimo_porcentaje_reportado = porcentaje
        self.update_state(
            state="PROGRESS",
            meta={
                "current": current,
                "total": total,
                "percent": min(100, porcentaje),
                "phase": phase,
                "message": message,
            },
        )

    try:
        with transaction.atomic():
            resultado = (
                cargar_matriculas(registros, actualizar_progreso)
                if carga.tipo == "Matrículas"
                else cargar_asistencia(registros, actualizar_progreso)
            )
    except ArchivoCargaError as exc:
        carga.estado = "error"
        carga.error = str(exc)
        carga.save(update_fields=["estado", "error", "actualizado_en"])
        raise

    carga.estado = "completada"
    carga.progreso_actual = carga.total
    carga.progreso_porcentaje = 100
    carga.etapa = "completada"
    carga.mensaje_progreso = "Carga completada."
    carga.resultado = resultado
    carga.save(update_fields=[
        "estado",
        "progreso_actual",
        "progreso_porcentaje",
        "etapa",
        "mensaje_progreso",
        "resultado",
        "actualizado_en",
    ])
    self.update_state(
        state="SUCCESS",
        meta={"current": total, "total": total, "percent": 100},
    )
    return resultado
