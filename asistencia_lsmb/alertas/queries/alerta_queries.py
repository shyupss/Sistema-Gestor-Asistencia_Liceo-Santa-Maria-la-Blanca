"""Alertas vigentes de un período, por curso y estado.

Una alerta cuenta solo si su alumno tiene matrícula activa (matriculas_activas)
en el período de la alerta; su curso es el de esa matrícula. Las tres funciones
reciben `periodo` como instancia o id, y `hoy` (por defecto timezone.localdate()).
Filtros opcionales: `cursos` (QuerySet o ids de Curso), `estados` (QuerySet o ids
de Estado, sobre el estado de la alerta) y `solo_sin_revisar`.
"""
from itertools import groupby

from django.db.models import F, IntegerField, OuterRef, QuerySet, Subquery
from django.utils import timezone

from academico.models import Curso
from alertas.models import Alerta, EstadoAlumno
from alertas.queries.matricula_queries import matriculas_activas
from alertas.services.niveles import nivel_alerta, umbral_critico


def _ids(valores):
    """QuerySet: subconsulta de sus pk. Iterable de instancias o ids: lista de ids."""
    if isinstance(valores, QuerySet):
        return valores.values("pk")
    return [getattr(valor, "pk", valor) for valor in valores]


def alertas_vigentes(periodo, cursos=None, estados=None, solo_sin_revisar=False, hoy=None):
    """Alertas vigentes del período de alumnos con matrícula activa en él, como QuerySet.

    Anota `curso_id` (curso de la matrícula activa; si hay más de una, la de
    mayor fecha_matricula y luego mayor id) y `porcentaje_asistencia` (del
    EstadoAlumno del mismo alumno y período; nulo si no hay). Incluye las
    revisadas salvo `solo_sin_revisar`. Orden: curso (nivel, grupo), estado más
    grave primero (menor umbral_minimo), porcentaje ascendente (nulos al final),
    nombre del alumno e id.
    """
    hoy = hoy or timezone.localdate()
    matricula = (
        matriculas_activas(hoy)
        .filter(alumno=OuterRef("alumno_id"), periodo=OuterRef("periodo_id"))
        .order_by("-fecha_matricula", "-pk")
    )
    estado_alumno = EstadoAlumno.objects.filter(
        alumno=OuterRef("alumno_id"), periodo=OuterRef("periodo_id"),
    )
    alertas = (
        Alerta.objects.filter(periodo=periodo, fecha_cierre__isnull=True)
        .annotate(
            curso_id=Subquery(matricula.values("curso_id")[:1], output_field=IntegerField()),
            porcentaje_asistencia=Subquery(estado_alumno.values("porcentaje_asistencia")[:1]),
        )
        .filter(curso_id__isnull=False)
        .select_related("alumno", "estado")
    )
    if cursos is not None:
        alertas = alertas.filter(curso_id__in=_ids(cursos))
    if estados is not None:
        alertas = alertas.filter(estado__in=_ids(estados))
    if solo_sin_revisar:
        alertas = alertas.filter(revisada=False)
    return alertas.order_by(
        Subquery(matricula.values("curso__nivel")[:1]),
        Subquery(matricula.values("curso__grupo")[:1]),
        "estado__umbral_minimo",
        F("porcentaje_asistencia").asc(nulls_last=True),
        "alumno__nombre",
        "pk",
    )


def cursos_marcados(periodo, cursos=None, estados=None, solo_sin_revisar=False, hoy=None):
    """Cursos con al menos una alerta de alertas_vigentes (mismos filtros), sin duplicados.

    QuerySet ordenado por (nivel, grupo). Una alerta revisada también marca el
    curso, salvo que se pida `solo_sin_revisar`.
    """
    alertas = alertas_vigentes(periodo, cursos, estados, solo_sin_revisar, hoy)
    return Curso.objects.filter(pk__in=alertas.values("curso_id")).order_by("nivel", "grupo", "pk")


def alertas_por_curso(periodo, cursos=None, estados=None, solo_sin_revisar=False, hoy=None):
    """Lista de (curso, [alertas]) en orden de curso, solo cursos con alertas; [] si no hay.

    Las alertas van en el orden de alertas_vigentes y cada una lleva el atributo
    `nivel` ("critico" o "atencion"). Hace un número fijo de consultas: las
    alertas, el umbral (una sola vez) y los cursos.
    """
    alertas = list(alertas_vigentes(periodo, cursos, estados, solo_sin_revisar, hoy))
    if not alertas:
        return []
    umbral = umbral_critico()
    cursos_por_id = Curso.objects.in_bulk({alerta.curso_id for alerta in alertas})
    resultado = []
    # alertas_vigentes ordena primero por curso: las de un curso quedan contiguas.
    for curso_id, del_curso in groupby(alertas, key=lambda alerta: alerta.curso_id):
        del_curso = list(del_curso)
        for alerta in del_curso:
            alerta.nivel = nivel_alerta(alerta.estado, umbral)
        resultado.append((cursos_por_id[curso_id], del_curso))
    return resultado
