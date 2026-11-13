from django.shortcuts import render
from django.utils import timezone
def pagina_reportes(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Reportes",
        "fecha_hoy": fecha_hoy,
        "tipos_reporte": [
            ("planilla", "Planilla de asistencia", "Excel, una hoja por curso", "layout-grid"),
            ("mensual", "Reporte mensual", "Resumen por curso", "calendar-days"),
            ("semestral", "Semestral y anual", "Evolución del periodo", "calendar-search"),
            ("alumno", "Ficha por alumno", "Historial individual", "user-round"),
            ("criticos", "Atención y críticos", "Alumnos en alerta", "triangle-alert"),
            ("justificaciones", "Justificaciones y retiros", "Por estado y fechas", "file-check-2"),
        ],
        "filtros": [("Periodo académico", ["2026", "2025"]), ("Rango", ["Semestre 1", "Semestre 2"]), ("Alcance", ["Todo el liceo", "Cursos específicos"])],
        "formatos": ["Excel", "PDF"],
        "indicadores": [("Asistencia general", "00,0%"), ("Meta", "00%"), ("Cursos", "12"), ("Alumnos en crítico", "00")],
        "encabezados": ["Curso", "Profesor jefe", "Alumnos", "Días trab.", "% asist.", "Estado"],
        "filas": [["1A", "Nombre apellido", "40", "000", "00,0%", "Óptimo"], ["1B", "Nombre apellido", "38", "000", "00,0%", "Atención"], ["1C", "Nombre apellido", "36", "000", "00,0%", "Crítico"]],
        "reportes_generados": [
            {"nombre": "Planilla, Semestre 1", "usuario": "Nombre", "fecha": "00/00/2026", "estado": "Listo"},
            {"nombre": "Mensual, Octubre", "usuario": "Nombre", "fecha": "00/00/2026", "estado": "Procesando 60%"},
        ],
    }
    return render(request, "reportes/base.html", contexto)