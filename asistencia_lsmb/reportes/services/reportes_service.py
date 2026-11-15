from datetime import date

from django.utils import timezone

from reportes.queries.reportes_query import (
    contar_alumnos_por_curso,
    obtener_cursos,
    obtener_resumen_por_curso,
)


def limite_semestre(periodo, semestre):
    """Devuelve el rango solicitado, acotado al período académico."""
    if semestre == "1":
        inicio, fin = date(periodo.anio, 1, 1), date(periodo.anio, 6, 30)
    else:
        inicio, fin = date(periodo.anio, 7, 1), date(periodo.anio, 12, 31)
    return max(periodo.fecha_inicio, inicio), min(periodo.fecha_fin, fin)


def resolver_filtros(request, periodos):
    anios = {str(periodo.anio): periodo for periodo in periodos}
    anio_actual = str(timezone.localdate().year)
    anio = request.GET.get("anio") or (
        anio_actual if anio_actual in anios else next(iter(anios), "")
    )
    periodo = anios.get(anio) or (periodos[0] if periodos else None)

    semestre = request.GET.get("semestre", "1")
    if semestre not in {"1", "2"}:
        semestre = "1"

    cursos = obtener_cursos(periodo)
    cursos_ids = {
        int(valor)
        for valor in request.GET.getlist("curso")
        if valor.isdigit()
    }
    cursos_seleccionados = [curso for curso in cursos if curso.pk in cursos_ids]
    return periodo, semestre, cursos, cursos_seleccionados


def preparar_vista_previa(periodo, semestre, cursos, cursos_seleccionados):
    if not periodo:
        return {
            "filas": [],
            "indicadores": [
                ("Asistencia general", "0.0%"),
                ("Ausencias", "0"),
                ("Cursos", "0"),
                ("Registros", "0"),
            ],
            "fecha_inicio": None,
            "fecha_fin": None,
        }

    fecha_inicio, fecha_fin = limite_semestre(periodo, semestre)
    cursos_filtrados = cursos_seleccionados or cursos
    resumen = obtener_resumen_por_curso(
        periodo,
        fecha_inicio,
        fecha_fin,
        cursos_filtrados,
    )

    filas = []
    total_registros = total_ausencias = 0
    for curso in cursos_filtrados:
        datos = resumen.get(curso.pk, {"total": 0, "ausencias": 0, "dias": 0})
        total = datos["total"]
        ausencias = datos["ausencias"]
        total_registros += total
        total_ausencias += ausencias
        asistencia = (total - ausencias) * 100 / total if total else None
        filas.append([
            f"{curso.nivel_romano}°{curso.grupo}",
            curso.profesor_jefe.nombre if curso.profesor_jefe else "Sin asignar",
            contar_alumnos_por_curso(curso, periodo, fecha_inicio, fecha_fin),
            datos["dias"],
            f"{asistencia:.1f}%" if asistencia is not None else "Sin datos",
            (
                "Óptimo"
                if asistencia is not None and asistencia >= 90
                else "Atención" if asistencia is not None else "Sin datos"
            ),
        ])

    porcentaje = (
        (total_registros - total_ausencias) * 100 / total_registros
        if total_registros
        else 0
    )
    return {
        "filas": filas,
        "indicadores": [
            ("Asistencia general", f"{porcentaje:.1f}%"),
            ("Ausencias", str(total_ausencias)),
            ("Cursos", str(len(filas))),
            ("Registros", str(total_registros)),
        ],
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
