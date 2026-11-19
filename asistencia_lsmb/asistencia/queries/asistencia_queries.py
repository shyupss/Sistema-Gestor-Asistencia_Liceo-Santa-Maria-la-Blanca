from django.db.models import (
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from academico.models import Curso, Matricula
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia


def obtener_cursos(fecha=None):
    fecha = fecha or timezone.localdate()
    matricula_vigente = Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha)
    matriculas_activas = Prefetch(
        "matriculas",
        queryset=Matricula.objects.filter(
            periodo__anio=fecha.year,
        ).filter(matricula_vigente).select_related("alumno"),
        to_attr="matriculas_activas",
    )

    paso_lista_hoy = Paso_Lista.objects.filter(
        curso=OuterRef("pk"),
        fecha=fecha,
    )
    inicio_anio = fecha.replace(month=1, day=1)
    inicio_siguiente_anio = inicio_anio.replace(year=fecha.year + 1)
    total_estudiantes = (
        Matricula.objects.filter(
            curso=OuterRef("pk"),
            periodo__anio=fecha.year,
        )
        .filter(matricula_vigente)
        .order_by()
        .values("curso_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    asistencias_curso = (
        Asistencia_Alumnos.objects.filter(
            paso_lista__curso=OuterRef("pk"),
            paso_lista__fecha__gte=inicio_anio,
            paso_lista__fecha__lt=inicio_siguiente_anio,
            paso_lista__fecha__lte=fecha,
        )
        .order_by()
        .values("paso_lista__curso_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    ausencias_curso = (
        Asistencia_Alumnos.objects.filter(
            paso_lista__curso=OuterRef("pk"),
            paso_lista__fecha__gte=inicio_anio,
            paso_lista__fecha__lt=inicio_siguiente_anio,
            paso_lista__fecha__lte=fecha,
            tipo_asistencia__cuenta_como_ausencia=True,
        )
        .filter(
            Q(justificacion__isnull=True)
            | Q(justificacion__estado_solicitud__cubre_ausencia=False)
        )
        .order_by()
        .values("paso_lista__curso_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )

    return Curso.objects.prefetch_related(
        matriculas_activas
    ).annotate(
        total_estudiantes=Coalesce(
            Subquery(total_estudiantes, output_field=IntegerField()),
            0,
        ),
        total_registros=Coalesce(
            Subquery(asistencias_curso, output_field=IntegerField()),
            0,
        ),
        total_ausencias=Coalesce(
            Subquery(ausencias_curso, output_field=IntegerField()),
            0,
        ),
        registrada_hoy=Exists(paso_lista_hoy),
    ).filter(periodo__anio=fecha.year).order_by("nivel", "grupo")


def obtener_alumnos_curso(curso, fecha=None):
    fecha = fecha or timezone.localdate()
    return Matricula.objects.filter(
        curso=curso,
        periodo=curso.periodo,
    ).filter(
        Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha),
    ).select_related("alumno").order_by("alumno__nombre")


def obtener_tipos_asistencia():
    return Tipos_Asistencia.objects.order_by("id")


def obtener_asistencias(paso_lista):
    return dict(
        Asistencia_Alumnos.objects.filter(
            paso_lista=paso_lista,
        ).values_list("alumno_id", "tipo_asistencia_id")
    )


def obtener_paso_lista(curso, fecha):
    return Paso_Lista.objects.filter(
        curso=curso,
        fecha=fecha,
    ).first()