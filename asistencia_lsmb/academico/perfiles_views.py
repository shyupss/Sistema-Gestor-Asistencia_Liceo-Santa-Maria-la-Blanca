from django.db.models import Count, Exists, F, OuterRef, Q
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from academico.models import Alumno, Curso, Matricula
from academico.queries.academico_queries import obtener_estados_asistencia
from academico.services.academico_service import clasificar_asistencia
from alertas.models import Alerta, EstadoAlumno, HistorialEstadoAlumno
from asistencia.models import Asistencia_Alumnos, Justificaciones, Paso_Lista
from asistencia.queries.asistencia_queries import obtener_alumnos_curso


def perfil_curso(request, curso_id):
    fecha_hoy = timezone.localdate()
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
    pasos_lista = Paso_Lista.objects.filter(
        curso=curso,
        fecha__year=fecha_hoy.year,
    )
    asistencias = Asistencia_Alumnos.objects.filter(
        paso_lista__in=pasos_lista,
        alumno__matriculas__curso=curso,
        alumno__matriculas__periodo=curso.periodo,
    ).distinct()
    total_dias_clase = pasos_lista.values("fecha").distinct().count()
    total_ausencias = asistencias.filter(
        tipo_asistencia__cuenta_como_ausencia=True,
    ).count()
    total_registros = asistencias.count()
    total_presentes = total_registros - total_ausencias
    estados_asistencia = obtener_estados_asistencia()
    registros_por_alumno = {
        registro["alumno_id"]: registro
        for registro in asistencias.values("alumno_id").annotate(
            total=Count("id", distinct=True),
            ausencias=Count(
                "id",
                filter=Q(tipo_asistencia__cuenta_como_ausencia=True),
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
            porcentaje = round(
                (registro["total"] - registro["ausencias"])
                * 100
                / registro["total"]
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
            tipo_asistencia__cuenta_como_ausencia=True,
        ).count()
        porcentaje_mes = (
            round((registros_mes_total - ausencias_mes) * 100 / registros_mes_total)
            if registros_mes_total
            else None
        )
        x = round(8 + indice * (84 / intervalos_grafico), 2)
        y = round(90 - (porcentaje_mes or 0) * 0.8, 2)
        if porcentaje_mes is not None:
            puntos_grafico.append(f"{x},{y}")
        evolucion_mensual.append({
            "nombre": nombre_mes,
            "porcentaje": porcentaje_mes,
            "x": x,
            "y": y,
        })

    porcentaje_asistencia = (
        round(total_presentes * 100 / total_registros)
        if total_registros
        else None
    )
    estado_curso = (
        clasificar_asistencia(porcentaje_asistencia, estados_asistencia)
        if porcentaje_asistencia is not None
        else None
    )

    contexto = {
        "page_title": f"Perfil de {curso.nivel_romano}° Medio {curso.grupo}",
        "curso": curso,
        "matriculas": matriculas,
        "asistencias": asistencias,
        "resumen_diario": resumen_diario,
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
        "porcentaje_asistencia": porcentaje_asistencia,
        "tab": tab,
        "fecha_hoy": fecha_hoy,
        "registrada_hoy": pasos_lista.filter(fecha=fecha_hoy).exists(),
        "volver_url": request.GET.get("next") or "/cursos/",
    }
    return render(request, "academico/perfiles/perfil_curso.html", contexto)


def perfil_alumno(request, alumno_id):
    fecha_hoy = timezone.localdate()
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
        .select_related("tipo_asistencia", "paso_lista", "justificacion")
        .order_by("-paso_lista__fecha")
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
            tipo_asistencia__cuenta_como_ausencia=True
        ).count()
        porcentaje_mes = (
            round((dias_mes - ausencias_mes) * 100 / dias_mes)
            if dias_mes
            else None
        )
        punto = None
        if porcentaje_mes is not None:
            x = round(8 + indice * (84 / intervalos_grafico), 2)
            y = round(90 - porcentaje_mes * 0.8, 2)
            punto = f"{x},{y}"
            puntos_grafico.append(punto)
        evolucion_mensual.append({
            "nombre": nombre_mes,
            "porcentaje": porcentaje_mes,
            "x": round(8 + indice * (84 / intervalos_grafico), 2),
            "y": round(90 - (porcentaje_mes or 0) * 0.8, 2),
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
            round((total_dias_clase - total_ausencias) * 100 / total_dias_clase)
            if total_dias_clase
            else None
        ),
        "fecha_hoy": fecha_hoy,
        "volver_url": volver_url,
        "volver_label": volver_label,
    }
    return render(request, "academico/perfiles/perfil_alumno.html", contexto)