from django.db.models import Count, Q

from academico.models import Curso, Matricula
from alertas.models import Alerta, EstadoAlumno, HistorialEstadoAlumno
from asistencia.models import Asistencia_Alumnos, Paso_Lista


def obtener_periodo_actual(fecha):
    return (
        Curso.objects.filter(periodo__anio=fecha.year)
        .values_list("periodo", flat=True)
        .first()
    )


def obtener_cursos_periodo(periodo_id):
    return Curso.objects.filter(periodo_id=periodo_id).select_related(
        "periodo", "profesor_jefe"
    ).prefetch_related(
        "matriculas"
    ).order_by("nivel", "grupo")


def obtener_asistencias_periodo(periodo_id, fecha_fin):
    return Asistencia_Alumnos.objects.filter(
        paso_lista__curso__periodo_id=periodo_id,
        paso_lista__fecha__lte=fecha_fin,
    ).select_related("tipo_asistencia", "paso_lista")


def obtener_pasos_periodo(periodo_id, fecha_fin):
    return Paso_Lista.objects.filter(
        curso__periodo_id=periodo_id,
        fecha__lte=fecha_fin,
    )


def obtener_estados_alumnos(periodo_id):
    return EstadoAlumno.objects.filter(
        periodo_id=periodo_id,
    ).select_related("alumno", "estado")


def obtener_historial_alertas(periodo_id, fecha_fin):
    return HistorialEstadoAlumno.objects.filter(
        periodo_id=periodo_id,
        fecha_cambio__date__lte=fecha_fin,
        estado_nuevo__genera_alerta=True,
    ).select_related(
        "alumno", "estado_nuevo"
    ).order_by("-fecha_cambio")


def obtener_alertas(periodo_id, fecha_fin):
    return Alerta.objects.filter(
        periodo_id=periodo_id,
        fecha__date__lte=fecha_fin,
    ).select_related(
        "alumno", "estado", "periodo"
    ).order_by("-fecha")


def contar_asistencias(queryset):
    total = queryset.count()
    ausencias = queryset.filter(tipo_asistencia__cuenta_como_ausencia=True).count()
    return total, ausencias


def contar_matriculas_activas(curso, fecha):
    return Matricula.objects.filter(
        curso=curso,
        periodo=curso.periodo,
    ).filter(
        Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha),
    ).count()