from datetime import date
from io import BytesIO

from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from reportes.queries.reportes_query import (
    contar_alumnos_por_curso,
    obtener_cursos,
    obtener_resumen_por_curso,
)
from asistencia.models import Asistencia_Alumnos, Paso_Lista
from academico.models import Matricula


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
    parametros = request.POST if request.method == "POST" else request.GET
    anio = parametros.get("anio") or (
        anio_actual if anio_actual in anios else next(iter(anios), "")
    )
    periodo = anios.get(anio) or (periodos[0] if periodos else None)

    semestre = parametros.get("semestre", "1")
    if semestre not in {"1", "2"}:
        semestre = "1"

    cursos = obtener_cursos(periodo)
    cursos_ids = {
        int(valor)
        for valor in parametros.getlist("curso")
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


def obtener_datos_planilla_curso(curso, fecha_inicio, fecha_fin):
    matriculas = list(
        Matricula.objects.filter(
            curso=curso,
            periodo=curso.periodo,
            fecha_matricula__lte=fecha_fin,
        )
        .filter(
            Q(fecha_termino__isnull=True)
            | Q(fecha_termino__gte=fecha_inicio)
        )
        .select_related("alumno")
        .order_by("alumno__nombre")
    )

    asistencias = (
        Asistencia_Alumnos.objects.filter(
            paso_lista__curso=curso,
            paso_lista__fecha__gte=fecha_inicio,
            paso_lista__fecha__lte=fecha_fin,
        )
        .select_related(
            "alumno",
            "paso_lista",
            "tipo_asistencia",
            "justificacion__estado_solicitud",
        )
    )

    meses = {}
    fechas_trabajadas = set(
        Paso_Lista.objects.filter(
            curso=curso,
            fecha__gte=fecha_inicio,
            fecha__lte=fecha_fin,
        ).values_list("fecha", flat=True)
    )
    mes_actual = fecha_inicio.month
    anio_actual = fecha_inicio.year
    while date(anio_actual, mes_actual, 1) <= date(fecha_fin.year, fecha_fin.month, 1):
        meses[mes_actual] = set(
            paso_fecha
            for paso_fecha in fechas_trabajadas
            if paso_fecha.year == anio_actual and paso_fecha.month == mes_actual
        )
        if mes_actual == 12:
            mes_actual = 1
            anio_actual += 1
        else:
            mes_actual += 1

    conteos = {
        matricula.alumno_id: {
            mes: {"asistidos": set(), "licencias": set()}
            for mes in meses
        }
        for matricula in matriculas
    }
    for asistencia in asistencias:
        mes = asistencia.paso_lista.fecha.month
        alumno_id = asistencia.alumno_id
        if alumno_id not in conteos:
            continue
        clave_fecha = asistencia.paso_lista.fecha
        if asistencia.tipo_asistencia.cuenta_como_ausencia:
            justificacion = asistencia.justificacion
            if (
                justificacion
                and justificacion.estado_solicitud.cubre_ausencia
            ):
                conteos[alumno_id][mes]["licencias"].add(clave_fecha)
        else:
            conteos[alumno_id][mes]["asistidos"].add(clave_fecha)

    dias_trabajados = {}
    for mes, fechas in meses.items():
        dias_trabajados[mes] = len(fechas)

    filas = []
    for numero, matricula in enumerate(matriculas, start=1):
        alumno = matricula.alumno
        retirado = bool(
            matricula.fecha_termino
            and matricula.fecha_termino <= fecha_fin
        )
        mensual = conteos[alumno.pk]
        asistidos = sum(
            len(datos["asistidos"])
            for datos in mensual.values()
        )
        licencias = sum(
            len(datos["licencias"])
            for datos in mensual.values()
        )
        dias_total = sum(dias_trabajados.values())
        porcentaje = (
            None
            if retirado or dias_total == 0
            else (asistidos + licencias) / dias_total
        )
        filas.append({
            "numero": numero,
            "fecha_matricula": matricula.fecha_matricula,
            "fecha_retiro": matricula.fecha_termino,
            "nombre": alumno.nombre,
            "mensual": mensual,
            "asistidos": "Retirado" if retirado else asistidos,
            "licencias": licencias,
            "porcentaje": "Retirado" if retirado else porcentaje,
        })
    return meses, dias_trabajados, filas


def generar_planilla_excel(periodo, semestre, vista_previa, cursos):
    meses_nombre = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    workbook = Workbook()
    workbook.remove(workbook.active)

    fecha_inicio = vista_previa["fecha_inicio"]
    fecha_fin = vista_previa["fecha_fin"]

    for curso in cursos:
        nombre_hoja = f"{curso.nivel_romano}{curso.grupo}"
        hoja = workbook.create_sheet(title=nombre_hoja[:31])
        hoja.sheet_view.showGridLines = False
        hoja.freeze_panes = "F4"
        hoja.page_setup.orientation = "landscape"
        hoja.page_setup.fitToWidth = 1
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.page_margins = PageMargins(
            left=0.25,
            right=0.25,
            top=0.5,
            bottom=0.5,
        )

        meses, dias_trabajados, filas = obtener_datos_planilla_curso(
            curso,
            fecha_inicio,
            fecha_fin,
        )
        lista_meses = list(meses)

        hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
        hoja["A1"] = f"Cálculo Asistencia {curso.nivel_romano}° {curso.grupo}"
        hoja["A1"].font = Font(bold=True, size=14, color="FFFFFF")
        hoja["A1"].fill = PatternFill("solid", fgColor="1E3A8A")
        hoja["A1"].alignment = Alignment(horizontal="center")

        hoja.append([])
        hoja.append([])

        hoja["A2"] = "N°"
        hoja["B2"] = "Fecha Matrícula"
        hoja["C2"] = "Fecha Retiro"
        hoja["D2"] = "Nombre Alumno"
        encabezado_final = 4 + len(lista_meses) * 2 + 4
        for mes in lista_meses:
            col = 5 + (lista_meses.index(mes) * 2)
            hoja.cell(row=2, column=col, value=meses_nombre[mes - 1])
            hoja.cell(row=2, column=col + 1, value="")
            hoja.merge_cells(
                start_row=2,
                start_column=col,
                end_row=2,
                end_column=col + 1,
            )

        hoja.cell(row=2, column=encabezado_final - 3, value="Total Asistencia")
        hoja.cell(row=2, column=encabezado_final - 2, value="Total Licencias")
        hoja.cell(row=2, column=encabezado_final - 1, value="Justificaciones")
        hoja.cell(row=2, column=encabezado_final, value="% Asistencia")

        hoja["A3"] = "N°"
        hoja["B3"] = "Fecha Matrícula"
        hoja["C3"] = "Fecha Retiro"
        hoja["D3"] = "Nombre Alumno"
        for mes in lista_meses:
            col = 5 + (lista_meses.index(mes) * 2)
            hoja.cell(row=3, column=col, value="Días Asistidos")
            hoja.cell(row=3, column=col + 1, value="Días Licencia")
        hoja.cell(row=3, column=encabezado_final - 3, value="Total")
        hoja.cell(row=3, column=encabezado_final - 2, value="Total")
        hoja.cell(row=3, column=encabezado_final - 1, value="Cantidad")
        hoja.cell(row=3, column=encabezado_final, value="%")

        for mes in lista_meses:
            col = 5 + (lista_meses.index(mes) * 2)
            hoja.cell(row=1, column=col, value=f"Días Trabajados: {dias_trabajados[mes]}")
            hoja.merge_cells(
                start_row=1,
                start_column=col,
                end_row=1,
                end_column=col + 1,
            )

        for columna in range(1, encabezado_final + 1):
            for fila in (2, 3):
                celda = hoja.cell(row=fila, column=columna)
                celda.font = Font(bold=True, color="FFFFFF")
                celda.fill = PatternFill("solid", fgColor="1E3A8A")
                celda.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

        for fila_numero, fila in enumerate(filas, start=4):
            hoja.cell(row=fila_numero, column=1, value=fila["numero"])
            hoja.cell(row=fila_numero, column=2, value=fila["fecha_matricula"])
            hoja.cell(row=fila_numero, column=3, value=fila["fecha_retiro"])
            hoja.cell(row=fila_numero, column=4, value=fila["nombre"])
            for mes in lista_meses:
                col = 5 + (lista_meses.index(mes) * 2)
                datos = fila["mensual"][mes]
                hoja.cell(row=fila_numero, column=col, value=len(datos["asistidos"]))
                hoja.cell(row=fila_numero, column=col + 1, value=len(datos["licencias"]))
            hoja.cell(row=fila_numero, column=encabezado_final - 3, value=fila["asistidos"])
            hoja.cell(row=fila_numero, column=encabezado_final - 2, value=fila["licencias"])
            hoja.cell(row=fila_numero, column=encabezado_final - 1, value=fila["licencias"])
            porcentaje = fila["porcentaje"]
            hoja.cell(
                row=fila_numero,
                column=encabezado_final,
                value=porcentaje,
            )
            if isinstance(porcentaje, float):
                hoja.cell(row=fila_numero, column=encabezado_final).number_format = "0.0%"

            for columna in range(1, encabezado_final + 1):
                celda = hoja.cell(row=fila_numero, column=columna)
                celda.alignment = Alignment(vertical="center")

        anchos = {
            1: 6,
            2: 14,
            3: 14,
            4: 38,
        }
        for columna, ancho in anchos.items():
            hoja.column_dimensions[get_column_letter(columna)].width = ancho
        for columna in range(5, encabezado_final + 1):
            hoja.column_dimensions[get_column_letter(columna)].width = (
                17 if columna >= encabezado_final - 3 else 12
            )
        hoja.auto_filter.ref = f"A3:{get_column_letter(encabezado_final)}{3 + len(filas)}"

    archivo = BytesIO()
    workbook.save(archivo)
    archivo.seek(0)
    return ContentFile(
        archivo.getvalue(),
        name=f"planilla_asistencia_{periodo.anio}_semestre_{semestre}.xlsx",
    )
