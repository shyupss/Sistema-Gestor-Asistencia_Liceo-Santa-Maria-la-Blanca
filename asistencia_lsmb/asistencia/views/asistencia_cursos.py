from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from asistencia.queries.asistencia_queries import obtener_cursos
from asistencia.services.asistencia_service import preparar_cursos


def pagina_asistencia(request):
    fecha_hoy = timezone.localdate()
    cursos = obtener_cursos(fecha_hoy)
    cursos, resumen = preparar_cursos(cursos)
    total_cursos_periodo = len(cursos)
    total_cursos_registrados = sum(
        1 for curso in cursos if curso.registrada_hoy
    )

    search_query = request.GET.get("q", "")
    estado_filtro = request.GET.get("estado", "")

    cursos = [
        curso for curso in cursos
        if not search_query or search_query.lower() in (
            f"{curso.nivel_romano} medio {curso.grupo} {curso.profesor_jefe}"
        ).lower()
    ]

    if estado_filtro:
        cursos = [
            curso for curso in cursos
            if curso.estado_asistencia == estado_filtro
        ]

    cursos = [curso for curso in cursos if curso.pendiente]
    cursos_pendientes = cursos
    paginator = Paginator(cursos, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "page_obj": page_obj,
        "alertas": resumen["alertas"],
        "search_query": search_query,
        "estado_filtro": estado_filtro,
        "fecha_hoy": fecha_hoy,
        "current_year": fecha_hoy.year,
        "cursos_pendientes": cursos_pendientes,
        "total_cursos": len(cursos),
        "total_cursos_periodo": total_cursos_periodo,
        "total_cursos_registrados": total_cursos_registrados,
    }

    return render(request, "asistencia/cursos.html", contexto)