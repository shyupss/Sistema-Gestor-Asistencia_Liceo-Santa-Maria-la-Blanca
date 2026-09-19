from datetime import timedelta

from babel.dates import format_date
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import render
from django.utils import timezone

from academico.queries.academico_queries import (
    obtener_alumnos,
    obtener_cursos,
    obtener_estados_asistencia,
)
from academico.services.academico_service import (
    preparar_alumnos,
    preparar_cursos,
)


def _datos_fecha(fecha):
    inicio_semana = fecha - timedelta(days=fecha.weekday())
    return {
        "fecha_hoy": fecha,
        "current_year": fecha.year,
        "current_month": format_date(
            fecha, format="MMMM", locale="es"
        ).capitalize(),
        "inicio_semana": format_date(
            inicio_semana, format="dd MMM", locale="es"
        ),
        "fin_semana": format_date(
            inicio_semana + timedelta(days=6),
            format="dd MMM",
            locale="es",
        ),
    }


def _datos_paginacion(request, orden_predeterminado):
    try:
        per_page = int(request.GET.get("per_page", 12))
    except (TypeError, ValueError):
        per_page = 12
    if per_page not in {12, 24, 48}:
        per_page = 12

    orden = request.GET.get("orden", orden_predeterminado)
    return {
        "search_query": request.GET.get("q", ""),
        "estado_filtro": request.GET.get("estado", ""),
        "per_page": per_page,
        "orden": orden,
        "is_12": per_page == 12,
        "is_24": per_page == 24,
        "is_48": per_page == 48,
    }


def pagina_alumnos(request):
    fecha_hoy = timezone.localdate()
    parametros = _datos_paginacion(request, "asc")
    if parametros["orden"] not in {"asc", "desc"}:
        parametros["orden"] = "asc"

    estados = obtener_estados_asistencia()
    alumnos_base = obtener_alumnos(fecha_hoy)
    alumnos_con_datos, resumen = preparar_alumnos(alumnos_base, estados)
    alumnos_qs = alumnos_base

    if parametros["search_query"]:
        alumnos_qs = alumnos_qs.filter(
            Q(nombre__icontains=parametros["search_query"])
            | Q(rut__icontains=parametros["search_query"])
            | Q(matriculas__curso__grupo__icontains=parametros["search_query"])
        ).distinct()

    if parametros["estado_filtro"]:
        if parametros["estado_filtro"] == "Sin datos":
            alumnos_qs = alumnos_qs.filter(estado_alumno_nombre__isnull=True)
        else:
            alumnos_qs = alumnos_qs.filter(
                estado_alumno_nombre=parametros["estado_filtro"]
            )

    alumnos_qs = alumnos_qs.order_by(
        F("porcentaje_asistencia").desc(nulls_last=True)
        if parametros["orden"] == "desc"
        else F("porcentaje_asistencia").asc(nulls_last=True),
        "nombre",
    )
    page_obj = Paginator(
        alumnos_qs, parametros["per_page"]
    ).get_page(request.GET.get("page"))
    alumnos_clasificados = {alumno.pk: alumno for alumno in alumnos_con_datos}
    for alumno in page_obj:
        clasificado = alumnos_clasificados[alumno.pk]
        alumno.porcentaje_asistencia = clasificado.porcentaje_asistencia
        alumno.estado_asistencia = clasificado.estado_asistencia
        alumno.genera_alerta = clasificado.genera_alerta

    contexto = {
        "page_title": "Estudiantes",
        "page_obj": page_obj,
        **parametros,
        **_datos_fecha(fecha_hoy),
        "total": f'{resumen["total"]} Estudiantes',
        "estudiante_alerta": resumen["estudiante_alerta"],
        "porcentaje_general": resumen["porcentaje_general"],
        "porcentaje_alertas": resumen["porcentaje_alertas"],
        "pastillas": [
            (f'{resumen["total"]} Estudiantes · Periodo actual', "azul"),
            (f'Estudiantes con alerta · {resumen["estudiante_alerta"]}', "amarillo"),
        ],
        "alertas": resumen["alertas"],
    }
    return render(request, "academico/base.html", contexto)


def pagina_cursos(request):
    fecha_hoy = timezone.localdate()
    parametros = _datos_paginacion(request, "curso")
    if parametros["orden"] not in {"curso", "asc", "desc"}:
        parametros["orden"] = "curso"

    estados = obtener_estados_asistencia()
    cursos, resumen = preparar_cursos(
        obtener_cursos(fecha_hoy), fecha_hoy, estados
    )

    if parametros["orden"] in {"asc", "desc"}:
        cursos = sorted(
            cursos,
            key=lambda curso: (
                curso.total_registros == 0,
                -curso.asistencia
                if parametros["orden"] == "desc"
                else curso.asistencia,
            ),
        )

    cursos = [
        curso for curso in cursos
        if (
            not parametros["search_query"]
            or parametros["search_query"].lower() in (
                f"{curso.nivel_romano} medio {curso.grupo} {curso.profesor_jefe}"
            ).lower()
        )
        and (
            not parametros["estado_filtro"]
            or curso.estado_asistencia == parametros["estado_filtro"]
        )
    ]
    page_obj = Paginator(
        cursos, parametros["per_page"]
    ).get_page(request.GET.get("page"))

    contexto = {
        "page_title": "Cursos",
        "page_obj": page_obj,
        **parametros,
        **_datos_fecha(fecha_hoy),
        "porcentaje_general": resumen["porcentaje_general"],
        "total": f'{resumen["total"]} Cursos',
        "pastillas": [
            (f'{resumen["total"]} Cursos · Periodo actual', "azul"),
            (f'Cumplimiento meta · {resumen["cumplimiento_meta"]}%', "verde"),
        ],
        "alertas": resumen["alertas"],
        "porcentaje_meta": resumen["porcentaje_meta"],
        "cumplimiento_meta": resumen["cumplimiento_meta"],
        "cursos_sobre_meta": resumen["cursos_sobre_meta"],
    }
    return render(request, "academico/base.html", contexto)
