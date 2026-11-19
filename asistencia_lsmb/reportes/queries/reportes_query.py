from django.db.models import Count, Q

from academico.models import Curso, PeriodoAcademico
from asistencia.models import Asistencia_Alumnos


def obtener_periodos():
    return list(PeriodoAcademico.objects.order_by("-anio"))


def obtener_cursos(periodo):
    if not periodo:
        return []
    return list(
        Curso.objects.filter(periodo=periodo)
        .select_related("profesor_jefe")
        .order_by("nivel", "grupo")
    )


def obtener_resumen_por_curso(periodo, fecha_inicio, fecha_fin, cursos):
    return {
        item["paso_lista__curso_id"]: item
        for item in (
            Asistencia_Alumnos.objects.filter(
                paso_lista__curso__periodo=periodo,
                paso_lista__fecha__range=(fecha_inicio, fecha_fin),
                paso_lista__curso__in=cursos,
            )
            .values("paso_lista__curso_id")
            .annotate(
                total=Count("id"),
                ausencias=Count(
                    "id",
                    filter=(
                        Q(tipo_asistencia__cuenta_como_ausencia=True)
                        & (
                            Q(justificacion__isnull=True)
                            | Q(justificacion__estado_solicitud__cubre_ausencia=False)
                        )
                    ),
                ),
                dias=Count("paso_lista__fecha", distinct=True),
            )
        )
    }


def contar_alumnos_por_curso(curso, periodo, fecha_inicio, fecha_fin):
    return (
        curso.matriculas.filter(
            periodo=periodo,
            fecha_matricula__lte=fecha_fin,
        )
        .filter(
            Q(fecha_termino__isnull=True) | Q(fecha_termino__gte=fecha_inicio)
        )
        .values("alumno_id")
        .distinct()
        .count()
    )
