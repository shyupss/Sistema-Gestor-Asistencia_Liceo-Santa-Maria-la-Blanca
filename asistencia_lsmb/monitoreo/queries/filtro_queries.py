from django.db.models import Count, Q
from django.utils import timezone
from academico.models import Alumno, Curso, Matricula, PeriodoAcademico
from asistencia.models import Asistencia_Alumnos, Justificaciones, Paso_Lista
from alertas.models import Alerta, EstadoAlumno, Funcionario, HistorialEstadoAlumno


def obtener_periodo_activo(fecha):
    """Obtiene el PeriodoAcademico activo para el año de la fecha dada."""
    return PeriodoAcademico.objects.filter(anio=fecha.year).first()


def obtener_asistencias_base(periodo_id, fecha_fin=None):
    """Obtiene el QuerySet base de Asistencia_Alumnos para el periodo."""
    qs = Asistencia_Alumnos.objects.filter(
        paso_lista__curso__periodo_id=periodo_id,
    )
    if fecha_fin:
        qs = qs.filter(paso_lista__fecha__lte=fecha_fin)
    return qs.select_related("tipo_asistencia", "paso_lista", "paso_lista__curso")


def filtrar_asistencias(queryset, curso_id=None, nivel=None, mes=None):
    """
    Aplica filtros combinados sobre un QuerySet de Asistencia_Alumnos.
    - curso_id: Filtra por el curso específico.
    - nivel: Filtra por nivel (1, 2, 3, 4). Si viene curso_id, curso_id toma precedencia.
    - mes: Filtra por el número de mes (1 al 12).
    """
    qs = queryset

    if curso_id:
        qs = qs.filter(paso_lista__curso_id=curso_id)
    elif nivel:
        qs = qs.filter(paso_lista__curso__nivel=nivel)

    if mes:
        qs = qs.filter(paso_lista__fecha__month=mes)

    return qs


def contar_asistencias(queryset):
    """Retorna la tupla (total, ausencias) para el QuerySet de asistencias."""
    total = queryset.count()
    ausencias = queryset.filter(tipo_asistencia__cuenta_como_ausencia=True).count()
    return total, ausencias


def obtener_resumen_asistencias_por_dia(
    periodo_id,
    anio,
    mes,
    curso_id=None,
    nivel=None,
    fecha_inicio=None,
    fecha_fin=None,
):
    """
    Retorna un diccionario {fecha: (total, ausencias)} para cada día del mes
    que tenga registros de asistencia en una sola consulta agrupada.
    """
    qs = Asistencia_Alumnos.objects.filter(
        paso_lista__curso__periodo_id=periodo_id,
        paso_lista__fecha__year=anio,
        paso_lista__fecha__month=mes,
    )
    if fecha_inicio:
        qs = qs.filter(paso_lista__fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(paso_lista__fecha__lte=fecha_fin)
    qs = filtrar_asistencias(qs, curso_id=curso_id, nivel=nivel)

    resumen = qs.values("paso_lista__fecha").annotate(
        total=Count("id"),
        ausencias=Count("id", filter=Q(tipo_asistencia__cuenta_como_ausencia=True)),
    )
    return {
        item["paso_lista__fecha"]: (item["total"], item["ausencias"])
        for item in resumen
    }


def obtener_cursos_disponibles(periodo_id):
    """Retorna los cursos del periodo ordenados por nivel y grupo."""
    return Curso.objects.filter(periodo_id=periodo_id).select_related("profesor_jefe").order_by("nivel", "grupo")


def obtener_alumnos_ids_activos(periodo_id, fecha, curso_id=None, nivel=None):
    """Obtiene alumnos matriculados y vigentes en un periodo y fecha dados."""
    qs = Matricula.objects.filter(
        periodo_id=periodo_id,
        fecha_matricula__lte=fecha,
    ).filter(
        Q(fecha_termino__isnull=True) | Q(fecha_termino__gte=fecha)
    )

    if curso_id:
        qs = qs.filter(curso_id=curso_id)
    elif nivel:
        qs = qs.filter(curso__nivel=nivel)

    return set(qs.values_list("alumno_id", flat=True))


def obtener_alumnos_ids_por_filtro(periodo_id, fecha, curso_id=None, nivel=None):
    """
    Retorna un set con los IDs de alumnos que tienen matrícula activa
    en el periodo y fecha dados, filtrados opcionalmente por curso o nivel.
    Si no hay filtro de curso ni nivel, retorna None (sin restricción).
    """
    if not curso_id and not nivel:
        return None

    return obtener_alumnos_ids_activos(
        periodo_id,
        fecha,
        curso_id=curso_id,
        nivel=nivel,
    )


def obtener_estados_alumnos_filtrados(periodo_id, fecha, curso_id=None, nivel=None):
    """
    Obtiene los EstadoAlumno activos para el periodo, filtrados opcionalmente por curso o nivel.
    """
    qs = EstadoAlumno.objects.filter(
        periodo_id=periodo_id,
    ).select_related("alumno", "estado")

    alumno_ids = obtener_alumnos_ids_por_filtro(periodo_id, fecha, curso_id=curso_id, nivel=nivel)
    if alumno_ids is not None:
        qs = qs.filter(alumno_id__in=alumno_ids)

    return qs


def obtener_historial_alertas_filtrado(periodo_id, fecha_fin, curso_id=None, nivel=None):
    """
    Obtiene el HistorialEstadoAlumno hasta la fecha_fin, filtrado opcionalmente por curso o nivel.
    """
    qs = HistorialEstadoAlumno.objects.filter(
        periodo_id=periodo_id,
        fecha_cambio__date__lte=fecha_fin,
        estado_nuevo__genera_alerta=True,
    ).select_related("alumno", "estado_nuevo")

    alumno_ids = obtener_alumnos_ids_por_filtro(periodo_id, fecha_fin, curso_id=curso_id, nivel=nivel)
    if alumno_ids is not None:
        qs = qs.filter(alumno_id__in=alumno_ids)

    return qs.order_by("-fecha_cambio")


# =========================================================================
# QUERIES PARA JUSTIFICACIONES Y ACTIVIDAD RECIENTE
# =========================================================================

def obtener_justificaciones_pendientes_filtradas(fecha, alumno_ids=None):
    """
    Obtiene las justificaciones pendientes de revisión hasta la fecha dada,
    filtrables opcionalmente por un conjunto de IDs de alumnos.
    """
    qs = Justificaciones.objects.filter(
        estado_solicitud__nombre__iexact="pendiente",
        fecha_registro__date__lte=fecha,
    ).select_related("alumno", "estado_solicitud")

    if alumno_ids is not None:
        qs = qs.filter(alumno_id__in=alumno_ids)

    return qs.order_by("fecha_registro", "id")


def obtener_justificaciones_resueltas_filtradas(fecha, alumno_ids=None):
    """
    Obtiene las justificaciones resueltas hasta la fecha dada,
    filtrables opcionalmente por un conjunto de IDs de alumnos.
    """
    qs = Justificaciones.objects.filter(
        fecha_registro__date__lte=fecha,
        fecha_resolucion__isnull=False,
    ).select_related("alumno", "funcionario_resuelve")

    if alumno_ids is not None:
        qs = qs.filter(alumno_id__in=alumno_ids)

    return qs.order_by("-fecha_resolucion")


def obtener_funcionarios_disponibles():
    """Retorna los funcionarios activos con su cargo cargado."""
    return Funcionario.objects.filter(activo=True).select_related("cargo").order_by("nombre")


def obtener_alumnos_activos(periodo_id, fecha=None):
    """Retorna alumnos con matrícula vigente en el periodo y fecha dados."""
    if not periodo_id:
        return []
    fecha = fecha or timezone.localdate()
    matriculas = Matricula.objects.filter(
        periodo_id=periodo_id,
        fecha_matricula__lte=fecha,
    ).filter(
        Q(fecha_termino__isnull=True) | Q(fecha_termino__gte=fecha),
    ).select_related("alumno", "curso").order_by("alumno__nombre")
    return [
        {
            "id": m.alumno_id,
            "nombre": m.alumno.nombre,
            "curso": f"{m.curso.nivel_romano}°{m.curso.grupo}",
            "curso_id": m.curso_id,
        }
        for m in matriculas
    ]
