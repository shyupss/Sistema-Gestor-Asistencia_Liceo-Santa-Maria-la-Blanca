from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Exists,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
    IntegerField,
)
from django.db.models.functions import Coalesce

from academico.models import Alumno, Curso, Matricula
from asistencia.models import Asistencia_Alumnos, Paso_Lista
from alertas.models import EstadoAlumno


def obtener_alumnos(fecha):
    inicio_anio = fecha.replace(month=1, day=1)
    inicio_siguiente_anio = inicio_anio.replace(year=fecha.year + 1)
    matriculas_activas = Prefetch(
        "matriculas",
        queryset=Matricula.objects.filter(
            periodo__anio=fecha.year,
        ).filter(
            Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha),
        ).select_related("curso", "curso__periodo"),
        to_attr="matricula_activa_list",
    )
    asistencias_del_anio = Prefetch(
        "asistencia_alumnos_set",
        queryset=Asistencia_Alumnos.objects.filter(
            paso_lista__fecha__gte=inicio_anio,
            paso_lista__fecha__lt=inicio_siguiente_anio,
            paso_lista__fecha__lte=fecha,
            paso_lista__curso__periodo__anio=fecha.year,
        ).select_related(
            "tipo_asistencia",
            "justificacion__estado_solicitud",
        ),
        to_attr="asistencias_del_anio",
    )
    estado_actual = EstadoAlumno.objects.filter(
        alumno=OuterRef("pk"),
        periodo__anio=fecha.year,
    ).order_by()

    return Alumno.objects.prefetch_related(
        matriculas_activas,
        asistencias_del_anio,
    ).annotate(
        estado_alumno_porcentaje=Subquery(
            estado_actual.values("porcentaje_asistencia")[:1]
        ),
        estado_alumno_nombre=Subquery(
            estado_actual.values("estado__nombre")[:1]
        ),
        estado_alumno_alerta=Subquery(
            estado_actual.values("estado__es_no_ideal")[:1]
        ),
    ).annotate(
        porcentaje_asistencia=F("estado_alumno_porcentaje"),
    )


def obtener_cursos(fecha):
    paso_lista_hoy = Paso_Lista.objects.filter(
        curso=OuterRef("pk"),
        fecha=fecha,
    )
    matriculas_activas = Prefetch(
        "matriculas",
        queryset=Matricula.objects.filter(
            periodo__anio=fecha.year,
        ).filter(
            Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha),
        ).select_related("alumno"),
        to_attr="matriculas_activas",
    )
    return Curso.objects.filter(
        periodo__anio=fecha.year,
    ).order_by("nivel", "grupo").prefetch_related(matriculas_activas).annotate(
        total_estudiantes=Count(
            "matriculas",
            filter=Q(matriculas__periodo__anio=fecha.year)
            & (
                Q(matriculas__fecha_termino__isnull=True)
                | Q(matriculas__fecha_termino__gt=fecha)
            ),
            distinct=True,
        ),
        registrada_hoy=Exists(paso_lista_hoy),
    )


def obtener_asistencia_alumnos_curso(curso, alumno_ids, fecha):
    inicio_anio = fecha.replace(month=1, day=1)
    inicio_siguiente_anio = inicio_anio.replace(year=fecha.year + 1)
    return Asistencia_Alumnos.objects.filter(
        alumno_id__in=alumno_ids,
        paso_lista__fecha__gte=inicio_anio,
        paso_lista__fecha__lt=inicio_siguiente_anio,
        paso_lista__fecha__lte=fecha,
        paso_lista__curso__periodo=curso.periodo,
    )


def obtener_asistencia_curso(curso, fecha, alumno_ids=None):
    if alumno_ids is None:
        alumno_ids = Matricula.objects.filter(
            curso=curso,
            periodo=curso.periodo,
        ).filter(
            Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha),
        ).values_list("alumno_id", flat=True)

    asistencias = obtener_asistencia_alumnos_curso(curso, alumno_ids, fecha)
    resumen = asistencias.aggregate(
        total=Count("pk", distinct=True),
        ausencias=Count(
            "pk",
            filter=(
                Q(tipo_asistencia__cuenta_como_ausencia=True)
                & (
                    Q(justificacion__isnull=True)
                    | Q(justificacion__estado_solicitud__cubre_ausencia=False)
                )
            ),
            distinct=True,
        ),
    )
    resumen["porcentajes_alumnos"] = asistencias.values("alumno_id").annotate(
        total=Count("pk", distinct=True),
        ausencias=Count(
            "pk",
            filter=(
                Q(tipo_asistencia__cuenta_como_ausencia=True)
                & (
                    Q(justificacion__isnull=True)
                    | Q(justificacion__estado_solicitud__cubre_ausencia=False)
                )
            ),
            distinct=True,
        ),
    )
    return resumen


def obtener_resumen_asistencia_cursos(cursos, fecha):
    cursos = list(cursos)
    if not cursos:
        return {}

    alumno_ids_por_curso = {
        curso.pk: [
            matricula.alumno_id
            for matricula in curso.matriculas_activas
        ]
        for curso in cursos
    }
    alumno_ids = {
        alumno_id
        for ids in alumno_ids_por_curso.values()
        for alumno_id in ids
    }
    inicio_anio = fecha.replace(month=1, day=1)
    inicio_siguiente_anio = inicio_anio.replace(year=fecha.year + 1)
    filtros_ausencia = (
        Q(tipo_asistencia__cuenta_como_ausencia=True)
        & (
            Q(justificacion__isnull=True)
            | Q(justificacion__estado_solicitud__cubre_ausencia=False)
        )
    )
    asistencias = Asistencia_Alumnos.objects.filter(
        alumno_id__in=alumno_ids,
        paso_lista__curso_id__in=[curso.pk for curso in cursos],
        paso_lista__fecha__gte=inicio_anio,
        paso_lista__fecha__lt=inicio_siguiente_anio,
        paso_lista__fecha__lte=fecha,
    )
    totales = {}
    for fila in asistencias.values("paso_lista__curso_id").annotate(
        total=Count("pk", distinct=True),
        ausencias=Count("pk", filter=filtros_ausencia, distinct=True),
    ):
        totales[fila["paso_lista__curso_id"]] = fila

    porcentajes = {}
    for fila in asistencias.values(
        "paso_lista__curso_id",
        "alumno_id",
    ).annotate(
        total=Count("pk", distinct=True),
        ausencias=Count("pk", filter=filtros_ausencia, distinct=True),
    ):
        porcentajes.setdefault(fila["paso_lista__curso_id"], []).append(fila)

    return {
        curso.pk: {
            "total": totales.get(curso.pk, {}).get("total", 0),
            "ausencias": totales.get(curso.pk, {}).get("ausencias", 0),
            "porcentajes_alumnos": porcentajes.get(curso.pk, []),
        }
        for curso in cursos
    }


def obtener_estados_asistencia():
    from alertas.models import Estado

    return list(Estado.objects.order_by("-umbral_minimo"))
