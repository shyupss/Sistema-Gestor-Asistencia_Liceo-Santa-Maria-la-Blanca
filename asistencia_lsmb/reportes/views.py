from django.http import FileResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone

from reportes.queries.reportes_query import obtener_periodos
from reportes.models import ReporteGenerado
from reportes.services.reportes_service import (
    generar_planilla_excel,
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
        "reportes_generados": ReporteGenerado.objects.select_related(
            "generado_por",
            "periodo",
        ).all(),
        **vista_previa,
    }
    return render(request, "reportes/base.html", contexto)


def generar_reporte(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido.")

    tipo = request.POST.get("reporte", "")
    formato = request.POST.get("formato", "Excel")
    if tipo != "planilla" or formato != "Excel":
        return HttpResponseBadRequest("Solo está disponible la planilla en Excel.")

    periodos = obtener_periodos()
    periodo, semestre, cursos, cursos_seleccionados = resolver_filtros(
        request,
        periodos,
    )
    if periodo is None:
        return HttpResponseBadRequest("Debes seleccionar un período académico.")

    vista_previa = preparar_vista_previa(
        periodo,
        semestre,
        cursos,
        cursos_seleccionados,
    )
    archivo = generar_planilla_excel(
        periodo,
        semestre,
        vista_previa,
        cursos_seleccionados or cursos,
    )

    nombre = (
        f"Planilla de asistencia {periodo.anio} "
        f"- Semestre {semestre}"
    )
    reporte = ReporteGenerado(
        nombre=nombre,
        tipo="planilla",
        periodo=periodo,
        semestre=semestre,
        cursos_ids=[curso.pk for curso in (cursos_seleccionados or cursos)],
        filtros={
            "anio": str(periodo.anio),
            "semestre": semestre,
            "formato": formato,
        },
        estado="completado",
    )
    reporte.archivo.save(archivo.name, archivo, save=True)

    reporte.archivo.open("rb")
    return FileResponse(
        reporte.archivo.file,
        as_attachment=True,
        filename=archivo.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
