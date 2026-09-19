from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)

from academico.models import Alumno, Curso, Matricula
from asistencia.models import Asistencia_Alumnos
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
    asistencia_del_anio = Q(
        asistencia_alumnos__paso_lista__fecha__gte=inicio_anio,
        asistencia_alumnos__paso_lista__fecha__lt=inicio_siguiente_anio,
        asistencia_alumnos__paso_lista__curso__matriculas__alumno=F("pk"),
        asistencia_alumnos__paso_lista__curso__matriculas__periodo__anio=fecha.year,
    ) & (
        Q(asistencia_alumnos__paso_lista__curso__matriculas__fecha_termino__isnull=True)
        | Q(asistencia_alumnos__paso_lista__curso__matriculas__fecha_termino__gt=fecha)
    )
    estado_actual = EstadoAlumno.objects.filter(
        alumno=OuterRef("pk"),
        periodo__anio=fecha.year,
    ).order_by()

    return Alumno.objects.prefetch_related(matriculas_activas).annotate(
        estado_alumno_porcentaje=Subquery(
            estado_actual.values("porcentaje_asistencia")[:1]
        ),
        estado_alumno_nombre=Subquery(
            estado_actual.values("estado__nombre")[:1]
        ),
        estado_alumno_alerta=Subquery(
            estado_actual.values("estado__genera_alerta")[:1]
        ),
        total_asistencias=Count(
            "asistencia_alumnos",
            filter=asistencia_del_anio,
            distinct=True,
        ),
        total_ausencias=Count(
            "asistencia_alumnos",
            filter=asistencia_del_anio & Q(
                asistencia_alumnos__tipo_asistencia__cuenta_como_ausencia=True,
            ),
            distinct=True,
        ),
    ).annotate(
        porcentaje_asistencia=Case(
            When(
                total_asistencias__gt=0,
                then=ExpressionWrapper(
                    (F("total_asistencias") - F("total_ausencias"))
                    * Value(100.0) / F("total_asistencias"),
                    output_field=FloatField(),
                ),
            ),
            default=None,
            output_field=FloatField(),
        )
    )


def obtener_cursos(fecha):
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
        )
    )


def obtener_asistencia_curso(curso, fecha):
    inicio_anio = fecha.replace(month=1, day=1)
    inicio_siguiente_anio = inicio_anio.replace(year=fecha.year + 1)
    asistencias = Asistencia_Alumnos.objects.filter(
        paso_lista__curso=curso,
        paso_lista__fecha__gte=inicio_anio,
        paso_lista__fecha__lt=inicio_siguiente_anio,
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo__anio=fecha.year,
    ).filter(
        Q(alumno__matriculas__fecha_termino__isnull=True)
        | Q(alumno__matriculas__fecha_termino__gt=fecha)
    )
    return asistencias.aggregate(
        total=Count("pk", distinct=True),
        ausencias=Count(
            "pk",
            filter=Q(tipo_asistencia__cuenta_como_ausencia=True),
            distinct=True,
        ),
    )


def obtener_estados_asistencia():
    from alertas.models import Estado

    return list(Estado.objects.order_by("-umbral_minimo"))
