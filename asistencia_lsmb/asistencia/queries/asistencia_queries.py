from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.utils import timezone

from academico.models import Curso, Matricula
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia


def obtener_cursos(fecha=None):
    fecha = fecha or timezone.localdate()
    matriculas_activas = Prefetch(
        "matriculas",
        queryset=Matricula.objects.filter(
            periodo__anio=fecha.year,
            fecha_termino__isnull=True,
        ).select_related("alumno"),
        to_attr="matriculas_activas",
    )

    paso_lista_hoy = Paso_Lista.objects.filter(
        curso=OuterRef("pk"),
        fecha=fecha,
    )

    return Curso.objects.prefetch_related(
        matriculas_activas
    ).annotate(
        total_estudiantes=Count(
            "matriculas",
            filter=Q(
                matriculas__periodo__anio=fecha.year,
                matriculas__fecha_termino__isnull=True,
            ),
            distinct=True,
        ),
        total_registros=Count(
            "paso_lista__asistencia_alumnos",
            filter=Q(
                paso_lista__fecha__year=fecha.year,
                paso_lista__asistencia_alumnos__alumno__matriculas__periodo__anio=fecha.year,
                paso_lista__asistencia_alumnos__alumno__matriculas__fecha_termino__isnull=True,
            ),
            distinct=True,
        ),
        total_ausencias=Count(
            "paso_lista__asistencia_alumnos",
            filter=Q(
                paso_lista__fecha__year=fecha.year,
                paso_lista__asistencia_alumnos__tipo_asistencia__cuenta_como_ausencia=True,
                paso_lista__asistencia_alumnos__alumno__matriculas__periodo__anio=fecha.year,
                paso_lista__asistencia_alumnos__alumno__matriculas__fecha_termino__isnull=True,
            ),
            distinct=True,
        ),
        registros_hoy=Count(
            "paso_lista__asistencia_alumnos",
            filter=Q(
                paso_lista__fecha=fecha,
                paso_lista__asistencia_alumnos__alumno__matriculas__periodo__anio=fecha.year,
                paso_lista__asistencia_alumnos__alumno__matriculas__fecha_termino__isnull=True,
            ),
            distinct=True,
        ),
        registrada_hoy=Exists(paso_lista_hoy),
    ).filter(periodo__anio=fecha.year).order_by("nivel", "grupo")


def obtener_alumnos_curso(curso):
    return Matricula.objects.filter(
        curso=curso,
        periodo=curso.periodo,
        fecha_termino__isnull=True,
    ).select_related("alumno").order_by("alumno__nombre")


def obtener_tipos_asistencia():
    return Tipos_Asistencia.objects.order_by("id")


def obtener_asistencias(paso_lista):
    return dict(
        Asistencia_Alumnos.objects.filter(
            paso_lista=paso_lista,
        ).values_list("alumno_id", "tipo_asistencia_id")
    )


def obtener_paso_lista(curso, fecha, jornada):
    return Paso_Lista.objects.filter(
        curso=curso,
        fecha=fecha,
        jornada=jornada,
    ).first()