from django.core.paginator import Paginator
from django.db.models import Count, Exists, F, OuterRef, Q
from django.core.paginator import Paginator
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from datetime import date, timedelta

from academico.models import Alumno, Curso, Matricula
from academico.queries.academico_queries import (
    obtener_asistencia_alumnos_curso,
    obtener_estados_asistencia,
)
from academico.services.academico_service import (
    clasificar_asistencia,
    promedio_asistencia,
    porcentaje_asistencia,
)
from alertas.models import Alerta, EstadoAlumno, HistorialEstadoAlumno
from asistencia.models import Asistencia_Alumnos, Justificaciones, Paso_Lista
from asistencia.queries.asistencia_queries import obtener_alumnos_curso


def _fecha_filtro(request, fecha_hoy, default_vista="dia"):
    vista = request.GET.get("vista", default_vista)
    if vista not in {"dia", "semana", "mes"}:
        vista = "dia"
    mes = request.GET.get("mes", f"{fecha_hoy.year}-{fecha_hoy.month:02d}")
    try:
        inicio_mes = date.fromisoformat(f"{mes}-01")
        if inicio_mes.year != fecha_hoy.year:
            raise ValueError
    except ValueError:
        inicio_mes = date(fecha_hoy.year, fecha_hoy.month, 1)
        mes = inicio_mes.strftime("%Y-%m")
    semana_texto = request.GET.get("semana", fecha_hoy.isoformat())
    try:
        semana = date.fromisoformat(semana_texto)
        if semana.year != fecha_hoy.year:
            raise ValueError
    except ValueError:
        semana = fecha_hoy
        semana_texto = semana.isoformat()
    inicio_semana = semana - timedelta(days=semana.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    if vista == "mes":
        siguiente_mes = (
            date(inicio_mes.year + (inicio_mes.month == 12), inicio_mes.month % 12 + 1, 1)
        )
        fin_periodo = siguiente_mes - timedelta(days=1)
        inicio_periodo = inicio_mes
    elif vista == "semana":
        inicio_periodo, fin_periodo = inicio_semana, fin_semana
    else:
        inicio_periodo = fin_periodo = fecha_hoy
    return {
        "vista": vista,
        "mes": mes,
        "semana": semana_texto,
        "inicio_periodo": inicio_periodo,
        "fin_periodo": fin_periodo,
    }


def _semanas_del_mes(inicio_mes):
    siguiente_mes = date(
        inicio_mes.year + (inicio_mes.month == 12),
        inicio_mes.month % 12 + 1,
        1,
    )
    ultimo_dia = siguiente_mes - timedelta(days=1)
    inicio = inicio_mes - timedelta(days=inicio_mes.weekday())
    semanas = []
    while inicio <= ultimo_dia:
        fin = inicio + timedelta(days=6)
        semanas.append({
            "numero": len(semanas) + 1,
            "inicio": max(inicio, inicio_mes),
            "fin": min(fin, ultimo_dia),
        })
        inicio = fin + timedelta(days=1)
    return semanas


def _resumen_asistencia(registros, inicio, fin):
    registros = [
        registro for registro in registros
        if inicio <= registro.paso_lista.fecha <= fin
    ]
    dias = {registro.paso_lista.fecha for registro in registros}
    ausentes = sum(
        registro.tipo_asistencia.cuenta_como_ausencia
        and not (
            registro.justificacion
            and registro.justificacion.estado_solicitud.cubre_ausencia
        )
        for registro in registros
    )
    total_registros = len(registros)
    return {
        "dias": len(dias),
        "asistidos": total_registros - ausentes,
        "ausentes": ausentes,
        "justificados": sum(
            bool(registro.justificacion and registro.justificacion.estado_solicitud.cubre_ausencia)
            for registro in registros
        ),
        "porcentaje": (
            round((total_registros - ausentes) * 100 / total_registros)
            if total_registros else None
        ),
    }


def perfil_curso(request, curso_id):
    fecha_hoy = timezone.localdate()
    filtro_asistencia = _fecha_filtro(request, fecha_hoy, default_vista="mes")
    tab = request.GET.get("tab", "informacion")
    tabs_validas = {
        "informacion",
        "asistencia",
        "justificaciones",
        "alertas",
        "historial",
        "estudiantes",
    }
    if tab not in tabs_validas:
        tab = "informacion"

    curso = get_object_or_404(
        Curso.objects.select_related("periodo", "profesor_jefe"),
        pk=curso_id,
    )
    matriculas = list(obtener_alumnos_curso(curso, fecha_hoy))
    matriculas_paginadas = Paginator(matriculas, 20).get_page(
        request.GET.get("estudiantes_page")
    )
    alumno_ids = [matricula.alumno_id for matricula in matriculas]
    pasos_lista = Paso_Lista.objects.filter(
        curso=curso,
        fecha__year=fecha_hoy.year,
    )
    asistencias = Asistencia_Alumnos.objects.filter(
        paso_lista__in=pasos_lista,
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo=curso.periodo,
    ).select_related(
        "tipo_asistencia", "paso_lista", "justificacion__estado_solicitud"
    ).distinct()
    asistencias_alumnos = obtener_asistencia_alumnos_curso(
        curso,
        alumno_ids,
        fecha_hoy,
    )
    ausencia_no_cubierta = (
        Q(tipo_asistencia__cuenta_como_ausencia=True)
        & (
            Q(justificacion__isnull=True)
            | Q(justificacion__estado_solicitud__cubre_ausencia=False)
        )
    )
    total_dias_clase = pasos_lista.values("fecha").distinct().count()
    total_ausencias = asistencias.filter(
        tipo_asistencia__cuenta_como_ausencia=True,
    ).count()
    total_registros = asistencias.count()
    total_presentes = total_registros - asistencias.filter(ausencia_no_cubierta).count()
    estados_asistencia = obtener_estados_asistencia()
    registros_por_alumno = {
        registro["alumno_id"]: registro
        for registro in asistencias_alumnos.values("alumno_id").annotate(
            total=Count("id", distinct=True),
            ausencias=Count(
                "id",
                filter=ausencia_no_cubierta,
                distinct=True,
            ),
        )
    }
    niveles_asistencia = {estado.nombre: 0 for estado in estados_asistencia}
    niveles_asistencia.update({"Sin datos": 0, "Sin configurar": 0})
    porcentaje_meta = 75
    estudiantes_meta = 0
    estudiantes_bajo_meta = 0
    for matricula in matriculas:
        registro = registros_por_alumno.get(matricula.alumno_id)
        if registro and registro["total"]:
            porcentaje = porcentaje_asistencia(
                registro["total"],
                registro["ausencias"],
            )
            estado = clasificar_asistencia(porcentaje, estados_asistencia)
            nombre_estado = estado.nombre if estado else "Sin configurar"
            if porcentaje >= porcentaje_meta:
                estudiantes_meta += 1
            else:
                estudiantes_bajo_meta += 1
        else:
            porcentaje = None
            nombre_estado = "Sin datos"
        niveles_asistencia[nombre_estado] += 1
        matricula.porcentaje_asistencia = porcentaje
        matricula.estado_asistencia = nombre_estado
    resumen_diario = asistencias.values(
        fecha=F("paso_lista__fecha"),
    ).annotate(
        presentes=Count(
            "alumno_id",
            filter=Q(tipo_asistencia__cuenta_como_ausencia=False),
            distinct=True,
        ),
        ausentes=Count(
            "alumno_id",
            filter=Q(tipo_asistencia__cuenta_como_ausencia=True),
            distinct=True,
        ),
    ).order_by("-fecha")
    resumen_diario_page = Paginator(
        resumen_diario, 10
    ).get_page(request.GET.get("asistencia_page"))
    resumen_periodo = _resumen_asistencia(
        list(asistencias.select_related(
            "tipo_asistencia", "paso_lista", "justificacion__estado_solicitud"
        )),
        filtro_asistencia["inicio_periodo"],
        filtro_asistencia["fin_periodo"],
    )
    nombres_meses = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    meses_planilla = []
    for mes in range(1, 13):
        dias_trabajados = {
            registro.paso_lista.fecha
            for registro in asistencias
            if registro.paso_lista.fecha.month == mes
        }
        meses_planilla.append({
            "numero": mes,
            "nombre": nombres_meses[mes - 1],
            "dias_trabajados": len(dias_trabajados),
        })
    meses_semanas_planilla = []
    semanas_planilla = []
    for mes in meses_planilla:
        inicio_mes = date(fecha_hoy.year, mes["numero"], 1)
        semanas_mes = _semanas_del_mes(inicio_mes)
        for semana in semanas_mes:
            semana["mes_nombre"] = mes["nombre"]
        meses_semanas_planilla.append({
            "nombre": mes["nombre"],
            "semanas": semanas_mes,
            "columnas": len(semanas_mes) * 3,
        })
        semanas_planilla.extend(semanas_mes)
    registros_por_alumno_mes = {}
    for registro in asistencias.select_related(
        "tipo_asistencia", "paso_lista", "justificacion__estado_solicitud"
    ):
        clave = (registro.alumno_id, registro.paso_lista.fecha.month)
        registros_por_alumno_mes.setdefault(clave, []).append(registro)
    planilla_estudiantes = []
    for matricula in matriculas:
        meses = []
        for mes in meses_planilla:
            registros_mes = registros_por_alumno_mes.get(
                (matricula.alumno_id, mes["numero"]), []
            )
            ausencias = [
                registro for registro in registros_mes
                if registro.tipo_asistencia.cuenta_como_ausencia
                and not (
                    registro.justificacion
                    and registro.justificacion.estado_solicitud.cubre_ausencia
                )
            ]
            justificados = sum(
                bool(
                    registro.justificacion
                    and registro.justificacion.estado_solicitud.cubre_ausencia
                )
                for registro in registros_mes
            )
            asistidos = len(registros_mes) - len(ausencias)
            meses.append({
                "dias_trabajados": mes["dias_trabajados"],
                "asistidos": asistidos,
                "justificados": justificados,
                "porcentaje": (
                    round(asistidos * 100 / mes["dias_trabajados"])
                    if mes["dias_trabajados"] else None
                ),
            })
        planilla_estudiantes.append({
            "nombre": matricula.alumno.nombre,
            "meses": meses,
        })
    planilla_semanas = []
    for semana in semanas_planilla:
        estudiantes = []
        dias_trabajados = {
            registro.paso_lista.fecha
            for registro in asistencias
            if semana["inicio"] <= registro.paso_lista.fecha <= semana["fin"]
        }
        for matricula in matriculas:
            registros_semana = [
                registro for registro in registros_por_alumno_mes.get(
                    (matricula.alumno_id, semana["inicio"].month), []
                )
                if semana["inicio"] <= registro.paso_lista.fecha <= semana["fin"]
            ]
            ausencias = [
                registro for registro in registros_semana
                if registro.tipo_asistencia.cuenta_como_ausencia
                and not (
                    registro.justificacion
                    and registro.justificacion.estado_solicitud.cubre_ausencia
                )
            ]
            asistidos = len(registros_semana) - len(ausencias)
            justificados = sum(
                bool(
                    registro.justificacion
                    and registro.justificacion.estado_solicitud.cubre_ausencia
                )
                for registro in registros_semana
            )
            estudiantes.append({
                "asistidos": asistidos,
                "justificados": justificados,
                "porcentaje": (
                    round(asistidos * 100 / len(dias_trabajados))
                    if dias_trabajados else None
                ),
            })
        planilla_semanas.append({
            **semana,
            "dias_trabajados": len(dias_trabajados),
            "estudiantes": estudiantes,
        })
    for indice, estudiante in enumerate(planilla_estudiantes):
        estudiante["semanas"] = [
            semana["estudiantes"][indice] for semana in planilla_semanas
        ]
    solicitudes_aceptadas = Justificaciones.objects.filter(
        alumno_id=OuterRef("alumno_id"),
        estado_solicitud__nombre__iexact="aceptada",
        fecha_inicio__lte=OuterRef("paso_lista__fecha"),
        fecha_fin__gte=OuterRef("paso_lista__fecha"),
    )
    total_justificadas = asistencias.filter(
        tipo_asistencia__cuenta_como_ausencia=True,
    ).filter(Exists(solicitudes_aceptadas)).count()
    justificaciones = Justificaciones.objects.filter(
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo=curso.periodo,
        fecha_inicio__year=curso.periodo.anio,
    ).select_related(
        "alumno", "estado_solicitud", "funcionario_resuelve"
    ).distinct().order_by("-fecha_registro", "-id")
    total_solicitudes = justificaciones.count()
    solicitudes_pendientes = justificaciones.filter(
        estado_solicitud__nombre__iexact="pendiente"
    ).count()
    alertas = Alerta.objects.filter(
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo=curso.periodo,
        periodo=curso.periodo,
    ).select_related("alumno", "estado", "funcionario").distinct().order_by("-fecha")
    historial_estados = HistorialEstadoAlumno.objects.filter(
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo=curso.periodo,
        periodo=curso.periodo,
    ).select_related(
        "alumno", "estado_anterior", "estado_nuevo", "periodo"
    ).distinct().order_by("-fecha_cambio")

    nombres_meses = ("Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
    mes_inicial = 3
    intervalos_grafico = len(nombres_meses) - 1
    evolucion_mensual = []
    puntos_grafico = []
    for indice, nombre_mes in enumerate(nombres_meses):
        registros_mes = asistencias.filter(
            paso_lista__fecha__month=mes_inicial + indice,
        )
        registros_mes_total = registros_mes.count()
        ausencias_mes = registros_mes.filter(
            ausencia_no_cubierta,
        ).count()
        porcentaje_mes = (
            round((registros_mes_total - ausencias_mes) * 100 / registros_mes_total)
            if registros_mes_total
            else None
        )
        x = y = None
        if porcentaje_mes is not None:
            x = round(8 + indice * (84 / intervalos_grafico), 2)
            y = round(90 - porcentaje_mes * 0.8, 2)
            puntos_grafico.append(f"{x},{y}")
        evolucion_mensual.append({
            "nombre": nombre_mes,
            "porcentaje": porcentaje_mes,
            "x": x,
            "y": y,
        })

    porcentaje_curso = promedio_asistencia(
        registros_por_alumno.values()
    )
    estado_curso = (
        clasificar_asistencia(porcentaje_curso, estados_asistencia)
        if porcentaje_curso is not None
        else None
    )

    contexto = {
        "page_title": f"Perfil de {curso.nivel_romano}° Medio {curso.grupo}",
        "curso": curso,
        "matriculas": matriculas,
        "matriculas_paginadas": matriculas_paginadas,
        "asistencias": asistencias,
        "resumen_diario": resumen_diario_page,
        "resumen_periodo": resumen_periodo,
        "meses_planilla": meses_planilla,
        "planilla_estudiantes": planilla_estudiantes,
        "semanas_planilla": planilla_semanas,
        "meses_semanas_planilla": meses_semanas_planilla,
        "asistencia_vista": filtro_asistencia["vista"],
        "periodo_mes": filtro_asistencia["mes"],
        "periodo_semana": filtro_asistencia["semana"],
        "total_estudiantes": len(matriculas),
        "total_dias_clase": total_dias_clase,
        "total_registros": total_registros,
        "total_presentes": total_presentes,
        "total_ausencias": total_ausencias,
        "niveles_asistencia": niveles_asistencia,
        "porcentaje_meta": porcentaje_meta,
        "estudiantes_meta": estudiantes_meta,
        "estudiantes_bajo_meta": estudiantes_bajo_meta,
        "estado_asistencia": estado_curso.nombre if estado_curso else "Sin datos",
        "estado_genera_alerta": estado_curso.genera_alerta if estado_curso else False,
        "total_justificadas": total_justificadas,
        "total_sin_justificar": max(total_ausencias - total_justificadas, 0),
        "porcentaje_justificaciones": (
            round(total_justificadas * 100 / total_ausencias)
            if total_ausencias
            else 0
        ),
        "justificaciones": justificaciones,
        "total_solicitudes": total_solicitudes,
        "solicitudes_pendientes": solicitudes_pendientes,
        "alertas": alertas,
        "historial_estados": historial_estados,
        "evolucion_mensual": evolucion_mensual,
        "puntos_grafico": " ".join(puntos_grafico),
        "tab_items": [
            ("informacion", "Información"),
            ("asistencia", "Asistencia"),
            ("justificaciones", "Justificaciones"),
            ("alertas", "Alertas"),
            ("historial", "Historial"),
            ("estudiantes", "Estudiantes"),
        ],
        "porcentaje_asistencia": porcentaje_curso,
        "tab": tab,
        "fecha_hoy": fecha_hoy,
        "registrada_hoy": pasos_lista.filter(fecha=fecha_hoy).exists(),
        "volver_url": request.GET.get("next") or "/cursos/",
    }
    return render(request, "academico/perfiles/perfil_curso.html", contexto)


def perfil_alumno(request, alumno_id):
    fecha_hoy = timezone.localdate()
    filtro_asistencia = _fecha_filtro(request, fecha_hoy)
    tab = request.GET.get("tab", "informacion")
    tabs_validas = {"informacion", "asistencia", "justificaciones", "alertas", "historial"}
    if tab not in tabs_validas:
        tab = "informacion"

    alumno = get_object_or_404(Alumno, pk=alumno_id)
    matricula = (
        Matricula.objects.filter(alumno=alumno, periodo__anio=fecha_hoy.year)
        .filter(Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha_hoy))
        .select_related("curso", "periodo")
        .first()
    )
    registros_asistencia = (
        Asistencia_Alumnos.objects.filter(
            alumno=alumno,
            paso_lista__fecha__year=fecha_hoy.year,
        )
        .select_related(
            "tipo_asistencia",
            "paso_lista",
            "justificacion",
            "justificacion__estado_solicitud",
        )
        .order_by("-paso_lista__fecha")
    )
    registros_asistencia_lista = list(registros_asistencia)
    registros_asistencia_page = Paginator(
        registros_asistencia, 10
    ).get_page(request.GET.get("asistencia_page"))
    resumen_periodo = _resumen_asistencia(
        registros_asistencia_lista,
        filtro_asistencia["inicio_periodo"],
        filtro_asistencia["fin_periodo"],
    )
    nombres_meses = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    resumen_mensual = []
    for numero_mes, nombre_mes in enumerate(nombres_meses, start=1):
        resumen_mensual.append({
            "nombre": nombre_mes,
            **_resumen_asistencia(
                registros_asistencia_lista,
                date(fecha_hoy.year, numero_mes, 1),
                date(
                    fecha_hoy.year + (numero_mes == 12),
                    numero_mes % 12 + 1,
                    1,
                ) - timedelta(days=1),
            ),
        })
    inicio_mes_semanas = date.fromisoformat(f"{filtro_asistencia['mes']}-01")
    resumen_semanal = []
    for semana in _semanas_del_mes(inicio_mes_semanas):
        resumen_semanal.append({
            "nombre": f"Semana {semana['numero']}",
            "rango": f"{semana['inicio']:%d/%m} - {semana['fin']:%d/%m}",
            **_resumen_asistencia(
                registros_asistencia_lista,
                semana["inicio"],
                semana["fin"],
            ),
        })
    ausencia_no_cubierta = (
        Q(tipo_asistencia__cuenta_como_ausencia=True)
        & (
            Q(justificacion__isnull=True)
            | Q(justificacion__estado_solicitud__cubre_ausencia=False)
        )
    )
    total_dias_clase = registros_asistencia.values("paso_lista_id").distinct().count()
    total_ausencias = registros_asistencia.filter(
        tipo_asistencia__cuenta_como_ausencia=True
    ).count()
    solicitudes_aceptadas = Justificaciones.objects.filter(
        alumno_id=OuterRef("alumno_id"),
        estado_solicitud__nombre__iexact="aceptada",
        fecha_inicio__lte=OuterRef("paso_lista__fecha"),
        fecha_fin__gte=OuterRef("paso_lista__fecha"),
    )
    total_justificadas = registros_asistencia.filter(
        tipo_asistencia__cuenta_como_ausencia=True,
    ).filter(Exists(solicitudes_aceptadas)).count()
    nombres_meses = ("Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
    mes_inicial = 3
    intervalos_grafico = len(nombres_meses) - 1
    evolucion_mensual = []
    puntos_grafico = []
    for indice, nombre_mes in enumerate(nombres_meses):
        registros_mes = registros_asistencia.filter(
            paso_lista__fecha__month=mes_inicial + indice
        )
        dias_mes = registros_mes.values("paso_lista_id").distinct().count()
        ausencias_mes = registros_mes.filter(
            ausencia_no_cubierta
        ).count()
        porcentaje_mes = (
            round((dias_mes - ausencias_mes) * 100 / dias_mes)
            if dias_mes
            else None
        )
        x = y = None
        if porcentaje_mes is not None:
            x = round(8 + indice * (84 / intervalos_grafico), 2)
            y = round(90 - porcentaje_mes * 0.8, 2)
            puntos_grafico.append(f"{x},{y}")
        evolucion_mensual.append({
            "nombre": nombre_mes,
            "porcentaje": porcentaje_mes,
            "x": x,
            "y": y,
        })
    justificaciones = Justificaciones.objects.filter(alumno=alumno).select_related(
        "estado_solicitud", "funcionario_resuelve"
    ).order_by("-fecha_registro", "-id")
    total_solicitudes = justificaciones.count()
    solicitudes_pendientes = justificaciones.filter(
        estado_solicitud__nombre__iexact="pendiente"
    ).count()
    alertas = Alerta.objects.filter(alumno=alumno).select_related(
        "estado", "funcionario", "periodo"
    ).order_by("-fecha")
    estado_actual = (
        EstadoAlumno.objects.filter(alumno=alumno, periodo__anio=fecha_hoy.year)
        .select_related("estado", "periodo")
        .first()
    )
    historial_estados = HistorialEstadoAlumno.objects.filter(alumno=alumno).select_related(
        "estado_anterior", "estado_nuevo", "periodo"
    ).order_by("-fecha_cambio")

    volver_url = request.GET.get("next") or reverse("alumnos")
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "inicio"

    contexto = {
        "page_title": f"Perfil de {alumno.nombre}",
        "alumno": alumno,
        "matricula": matricula,
        "estado_actual": estado_actual,
        "registros_asistencia": registros_asistencia,
        "registros_asistencia_page": registros_asistencia_page,
        "resumen_periodo": resumen_periodo,
        "resumen_mensual": resumen_mensual,
        "resumen_semanal": resumen_semanal,
        "asistencia_vista": filtro_asistencia["vista"],
        "periodo_mes": filtro_asistencia["mes"],
        "periodo_semana": filtro_asistencia["semana"],
        "justificaciones": justificaciones,
        "total_solicitudes": total_solicitudes,
        "solicitudes_pendientes": solicitudes_pendientes,
        "alertas": alertas,
        "historial_estados": historial_estados,
        "tab": tab,
        "tab_items": [
            ("informacion", "Información"),
            ("asistencia", "Asistencia"),
            ("justificaciones", "Justificaciones"),
            ("alertas", "Alertas"),
            ("historial", "Historial"),
        ],
        "total_dias_clase": total_dias_clase,
        "total_presentes": total_dias_clase - total_ausencias,
        "total_ausencias": total_ausencias,
        "total_justificadas": total_justificadas,
        "total_sin_justificar": max(total_ausencias - total_justificadas, 0),
        "evolucion_mensual": evolucion_mensual,
        "puntos_grafico": " ".join(puntos_grafico),
        "porcentaje_justificaciones": (
            round(total_justificadas * 100 / total_ausencias)
            if total_ausencias
            else 0
        ),
        "porcentaje_asistencia": (
            round((
                total_dias_clase
                - registros_asistencia.filter(ausencia_no_cubierta).count()
            ) * 100 / total_dias_clase)
            if total_dias_clase
            else None
        ),
        "fecha_hoy": fecha_hoy,
        "volver_url": volver_url,
        "volver_label": volver_label,
    }
    return render(request, "academico/perfiles/perfil_alumno.html", contexto)