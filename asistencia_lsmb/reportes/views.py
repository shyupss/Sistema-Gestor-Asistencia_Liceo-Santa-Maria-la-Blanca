from django.shortcuts import render
from django.utils import timezone

from reportes.queries.reportes_query import obtener_periodos
from reportes.services.reportes_service import (
    preparar_vista_previa,
    resolver_filtros,
)


def pagina_reportes(request):
    fecha_hoy = timezone.localdate()
    periodos = obtener_periodos()
    periodo, semestre, cursos, cursos_seleccionados = resolver_filtros(
        request,
        periodos,
    )
    vista_previa = preparar_vista_previa(
        periodo,
        semestre,
        cursos,
        cursos_seleccionados,
    )

    contexto = {
        "page_title": "Reportes",
        "fecha_hoy": fecha_hoy,
        "tipos_reporte": [
            ("planilla", "Planilla de asistencia", "Resumen por curso", "layout-grid"),
            ("mensual", "Reporte mensual", "Resumen por curso", "calendar-days"),
            ("semestral", "Semestral y anual", "Evolución del periodo", "calendar-search"),
            ("alumno", "Ficha por alumno", "Historial individual", "user-round"),
            ("criticos", "Atención y críticos", "Alumnos en alerta", "triangle-alert"),
            ("justificaciones", "Justificaciones y retiros", "Por estado y fechas", "file-check-2"),
        ],
        "periodos": periodos,
        "periodo_seleccionado": periodo,
        "semestre_seleccionado": semestre,
        "cursos": cursos,
        "cursos_seleccionados": cursos_seleccionados,
        "encabezados": ["Curso", "Profesor jefe", "Alumnos", "Días trab.", "% asist.", "Estado"],
        "hay_datos": bool(vista_previa["filas"]),
        "reportes_generados": [],
        **vista_previa,
    }
    return render(request, "reportes/base.html", contexto)
