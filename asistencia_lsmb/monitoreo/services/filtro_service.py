import calendar
from datetime import date
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from academico.models import Curso, PeriodoAcademico
from alertas.models import Alerta, Funcionario
from asistencia.models import Justificaciones, Paso_Lista
from monitoreo.queries.filtro_queries import (
    contar_asistencias,
    filtrar_asistencias,
    obtener_alumnos_ids_activos,
    obtener_asistencias_base,
    obtener_cursos_disponibles,
    obtener_estados_alumnos_filtrados,
    obtener_historial_alertas_filtrado,
    obtener_justificaciones_pendientes_filtradas,
    obtener_justificaciones_resueltas_filtradas,
    obtener_periodo_activo,
    obtener_resumen_asistencias_por_dia,
)

MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
MESES_COMPLETOS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
)
NIVELES_ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV"}

MAPA_MESES = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}


def _porcentaje(total, ausencias):
    """Calcula el porcentaje de asistencia redondeado."""
    return round((total - ausencias) * 100 / total) if total else 0


def _rango_periodo(periodo, fecha):
    """Calcula la fecha de inicio y fin dentro del periodo académico hasta la fecha dada."""
    inicio = periodo.fecha_inicio
    fin = min(periodo.fecha_fin, fecha)
    return inicio, fin


def _parse_entero(valor, min_val=None, max_val=None):
    """Convierte un valor de request.GET a int si es válido, aplicando límites opcionales."""
    if valor is None or valor == "":
        return None
    try:
        num = int(valor)
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        return num
    except (TypeError, ValueError):
        return None


def _parse_mes(valor):
    """
    Parsea el mes tanto si viene como número (1-12) como si viene en texto
    ('octubre', 'oct', 'marzo', etc.).
    """
    if valor is None or valor == "":
        return None
    try:
        num = int(valor)
        if 1 <= num <= 12:
            return num
        return None
    except (TypeError, ValueError):
        pass

    val_limpio = str(valor).strip().lower()
    return MAPA_MESES.get(val_limpio, None)


def _nivel_alerta(nombre):
    """Clasifica el nombre de un estado en 'atencion' o 'critico'."""
    nombre = (nombre or "").lower()
    if "atenc" in nombre or "alerta" in nombre:
        return "atencion"
    return "critico"


def _tiempo_transcurrido(fecha_hora, ahora):
    """Devuelve un formato amigable de tiempo transcurrido (hace un momento, 5m, 2h, 3d)."""
    if not fecha_hora:
        return "hace un momento"
    if timezone.is_naive(fecha_hora):
        fecha_hora = timezone.make_aware(fecha_hora, timezone.get_current_timezone())
    if timezone.is_naive(ahora):
        ahora = timezone.make_aware(ahora, timezone.get_current_timezone())
    diferencia = ahora - fecha_hora
    minutos = int(diferencia.total_seconds() // 60)
    if minutos < 1:
        return "hace un momento"
    if minutos >= 1440:
        return f"{minutos // 1440}d"
    if minutos >= 60:
        return f"{minutos // 60}h"
    return f"{minutos}m"


def _curso_alumno(alumno, periodo_id=None, fecha=None):
    """Obtiene la matrícula vigente del alumno para recuperar su curso."""
    matriculas = alumno.matriculas.select_related("curso")
    if periodo_id:
        matriculas = matriculas.filter(periodo_id=periodo_id)
    if fecha:
        vigentes = matriculas.filter(fecha_matricula__lte=fecha).filter(
            Q(fecha_termino__isnull=True) | Q(fecha_termino__gte=fecha)
        )
        return vigentes.order_by("-fecha_matricula", "-id").first()
    return matriculas.filter(fecha_termino__isnull=True).first() or matriculas.first()


def _tipo_justificacion(valor):
    return "retiro" if valor == "retiro" else "justificacion"


def _nombre_normalizado(nombre):
    return (nombre or "").strip().lower()


def _parse_lista_tipos(get_params):
    """
    Parsea selecciones múltiples para tipos de actividad reciente.
    Soporta múltiples parámetros (?act_tipo=asistencia&act_tipo=retiro)
    o separados por coma (?act_tipo=asistencia,retiro).
    """
    def obtener_lista(clave):
        if hasattr(get_params, "getlist"):
            return get_params.getlist(clave)
        valor = get_params.get(clave)
        if valor is None:
            return []
        return list(valor) if isinstance(valor, (list, tuple)) else [valor]

    valores_raw = obtener_lista("act_tipo") or obtener_lista("tipo")

    if not valores_raw:
        return []

    resultado = set()
    for valor_raw in valores_raw:
        for v in str(valor_raw).split(","):
            v_clean = v.strip().lower()
            if "asist" in v_clean:
                resultado.add("asistencia")
            elif "just" in v_clean:
                resultado.add("justificacion")
            elif "retir" in v_clean:
                resultado.add("retiro")
            elif "alert" in v_clean:
                resultado.add("alerta")
    return list(resultado)


# =========================================================================
# RESOLUTORES DE FILTROS (request.GET)
# =========================================================================

def resolver_filtros_asistencia_general(get_params):
    """Filtros para 'Asistencia general': ag_curso, ag_nivel, ag_mes."""
    return {
        "curso": _parse_entero(get_params.get("ag_curso")),
        "nivel": _parse_entero(get_params.get("ag_nivel"), min_val=1, max_val=4),
        "mes": _parse_mes(get_params.get("ag_mes")),
    }


def resolver_filtros_evolucion(get_params):
    """Filtros para 'Evolución de asistencia': evo_curso, evo_nivel, evo_mes."""
    return {
        "curso": _parse_entero(get_params.get("evo_curso")),
        "nivel": _parse_entero(get_params.get("evo_nivel"), min_val=1, max_val=4),
        "mes": _parse_mes(get_params.get("evo_mes")),
    }


def resolver_filtros_alertas_nivel(get_params):
    """Filtros para 'Alertas por nivel': apn_curso / alerta_nivel_curso, apn_nivel / alerta_nivel_nivel."""
    curso_raw = get_params.get("apn_curso") or get_params.get("alerta_nivel_curso")
    nivel_raw = get_params.get("apn_nivel") or get_params.get("alerta_nivel_nivel")
    return {
        "curso": _parse_entero(curso_raw),
        "nivel": _parse_entero(nivel_raw, min_val=1, max_val=4),
    }


def resolver_filtros_tendencia_alertas(get_params):
    """Filtros para 'Tendencia de alertas activas': ten_curso / tendencia_curso, ten_nivel / tendencia_nivel."""
    curso_raw = get_params.get("ten_curso") or get_params.get("tendencia_curso")
    nivel_raw = get_params.get("ten_nivel") or get_params.get("tendencia_nivel")
    return {
        "curso": _parse_entero(curso_raw),
        "nivel": _parse_entero(nivel_raw, min_val=1, max_val=4),
    }


def resolver_filtros_justificaciones(get_params):
    """
    Filtros para 'Justificaciones pendientes por revisar':
    - just_curso / jp_curso: ID del curso
    - just_nivel / jp_nivel: Nivel (1 a 4)
    """
    curso_raw = get_params.get("just_curso") or get_params.get("jp_curso")
    nivel_raw = get_params.get("just_nivel") or get_params.get("jp_nivel")
    return {
        "curso": _parse_entero(curso_raw),
        "nivel": _parse_entero(nivel_raw, min_val=1, max_val=4),
    }


def resolver_filtros_actividad_reciente(get_params):
    """
    Filtros para 'Actividad reciente':
    - act_actor: 'sistema' o 'funcionario'
    - act_curso: ID del curso
    - act_tipo: lista múltiple de tipos ('asistencia', 'justificacion', 'retiro', 'alerta')
    """
    actor_raw = (get_params.get("act_actor") or get_params.get("actor") or "").strip().lower()
    actor_tipo = None

    if actor_raw in {"sistema", "system"}:
        actor_tipo = "sistema"
    elif actor_raw in {"funcionario", "funcionarios"}:
        actor_tipo = "funcionario"

    return {
        "actor": actor_tipo,
        "curso": _parse_entero(get_params.get("act_curso") or get_params.get("curso")),
        "tipos": _parse_lista_tipos(get_params),
    }


# =========================================================================
# CALCULADORES DE DASHBOARDS
# =========================================================================

def calcular_asistencia_general(periodo, fecha, filtros_ag):
    if not periodo:
        return {"porcentaje": 0, "meta": 75, "periodo": "Sin periodo académico"}

    inicio, fin = _rango_periodo(periodo, fecha)
    asistencias = obtener_asistencias_base(periodo.pk, fin).filter(
        paso_lista__fecha__gte=inicio,
    )

    asistencias_filtradas = filtrar_asistencias(
        asistencias,
        curso_id=filtros_ag.get("curso"),
        nivel=filtros_ag.get("nivel"),
        mes=filtros_ag.get("mes"),
    )

    total, ausencias = contar_asistencias(asistencias_filtradas)
    porcentaje = _porcentaje(total, ausencias)

    partes_descripcion = []
    mes = filtros_ag.get("mes")
    if mes:
        partes_descripcion.append(f"{MESES_COMPLETOS[mes - 1]} {periodo.anio}")
    else:
        partes_descripcion.append(f"Periodo académico {periodo.anio}")

    curso_id = filtros_ag.get("curso")
    nivel = filtros_ag.get("nivel")
    if curso_id:
        curso_obj = Curso.objects.filter(pk=curso_id).first()
        if curso_obj:
            partes_descripcion.append(f"{curso_obj.nivel_romano}° Medio {curso_obj.grupo}")
    elif nivel:
        partes_descripcion.append(f"{NIVELES_ROMANOS.get(nivel, nivel)}° Medio")

    return {
        "porcentaje": porcentaje,
        "meta": 75,
        "periodo": " · ".join(partes_descripcion),
        "total_registros": total,
        "ausencias": ausencias,
    }


def calcular_evolucion_asistencia(periodo, fecha, filtros_evo):
    if not periodo:
        return {"labels": [], "valores": [], "detalle_mes": None}

    inicio, fin = _rango_periodo(periodo, fecha)
    asistencias = obtener_asistencias_base(periodo.pk, fin).filter(
        paso_lista__fecha__gte=inicio,
    )

    asistencias_filtradas = filtrar_asistencias(
        asistencias,
        curso_id=filtros_evo.get("curso"),
        nivel=filtros_evo.get("nivel"),
    )

    labels = []
    valores = []
    meses = list(range(inicio.month, fin.month + 1)) if inicio <= fin else []
    for mes in meses:
        asistencias_mes = asistencias_filtradas.filter(paso_lista__fecha__month=mes)
        total_mes, ausencias_mes = contar_asistencias(asistencias_mes)
        labels.append(MESES[mes - 1])
        valores.append(_porcentaje(total_mes, ausencias_mes))

    detalle_mes = None
    mes_filtro = filtros_evo.get("mes")
    if mes_filtro:
        num_dias = calendar.monthrange(periodo.anio, mes_filtro)[1]
        resumen_dias = obtener_resumen_asistencias_por_dia(
            periodo.pk,
            periodo.anio,
            mes_filtro,
            curso_id=filtros_evo.get("curso"),
            nivel=filtros_evo.get("nivel"),
            fecha_inicio=inicio,
            fecha_fin=fin,
        )

        dias_labels = []
        dias_valores = []
        for dia_num in range(1, num_dias + 1):
            fecha_dia = date(periodo.anio, mes_filtro, dia_num)
            dias_labels.append(f"{dia_num:02d} {MESES[mes_filtro - 1]}")
            if fecha_dia in resumen_dias:
                total_dia, ausencias_dia = resumen_dias[fecha_dia]
                dias_valores.append(_porcentaje(total_dia, ausencias_dia))
            else:
                dias_valores.append(None)

        detalle_mes = {
            "mes_numero": mes_filtro,
            "mes_nombre": MESES_COMPLETOS[mes_filtro - 1],
            "labels": dias_labels,
            "valores": dias_valores,
        }

    return {
        "labels": labels,
        "valores": valores,
        "detalle_mes": detalle_mes,
        "mes_consultado": mes_filtro,
    }


def calcular_alertas_por_nivel(periodo, fecha, filtros_apn):
    if not periodo:
        return {
            "atencion": 0, "critico": 0, "total": 0,
            "pct_atencion": 0, "pct_critico": 0,
        }

    estados = list(obtener_estados_alumnos_filtrados(
        periodo.pk,
        fecha,
        curso_id=filtros_apn.get("curso"),
        nivel=filtros_apn.get("nivel"),
    ))

    estados_alerta = [e for e in estados if e.estado and e.estado.genera_alerta]
    atencion = sum(_nivel_alerta(e.estado.nombre) == "atencion" for e in estados_alerta)
    critico = sum(_nivel_alerta(e.estado.nombre) == "critico" for e in estados_alerta)
    total = atencion + critico

    return {
        "atencion": atencion,
        "critico": critico,
        "total": total,
        "pct_atencion": round(atencion * 100 / total) if total else 0,
        "pct_critico": round(critico * 100 / total) if total else 0,
    }


def calcular_tendencia_alertas(periodo, fecha, filtros_ten):
    if not periodo:
        return {"labels": [], "valores": []}

    historial = obtener_historial_alertas_filtrado(
        periodo.pk,
        fecha,
        curso_id=filtros_ten.get("curso"),
        nivel=filtros_ten.get("nivel"),
    )

    inicio, fin = _rango_periodo(periodo, fecha)
    labels = []
    valores = []
    meses = range(inicio.month, fin.month + 1) if inicio <= fin else []
    for mes in meses:
        labels.append(MESES[mes - 1])
        valores.append(historial.filter(fecha_cambio__month=mes).count())

    return {
        "labels": labels,
        "valores": valores,
    }


def calcular_justificaciones(periodo, fecha, filtros_just):
    """
    Calcula las justificaciones pendientes de revisión y las métricas
    aplicando filtros opcionales de curso y nivel.
    """
    curso_id = filtros_just.get("curso")
    nivel = filtros_just.get("nivel")

    alumno_ids = None
    if periodo:
        alumno_ids = obtener_alumnos_ids_activos(
            periodo.pk,
            fecha,
            curso_id=curso_id,
            nivel=nivel,
        )

    pendientes = list(obtener_justificaciones_pendientes_filtradas(fecha, alumno_ids=alumno_ids))
    resueltas = list(obtener_justificaciones_resueltas_filtradas(fecha, alumno_ids=alumno_ids))

    ahora = timezone.now()
    tiempos = [
        (item.fecha_resolucion - item.fecha_registro).total_seconds() / 86400
        for item in resueltas
        if item.fecha_resolucion and item.fecha_registro
    ]
    promedio = f"{sum(tiempos) / len(tiempos):.1f} días" if tiempos else "—"

    return {
        "justificaciones_pendientes": [
            {
                "alumno": item.alumno.nombre,
                "motivo": item.resumen or item.motivo or "Sin motivo indicado",
                "tiempo": _tiempo_transcurrido(item.fecha_registro, ahora),
                "url": reverse("perfil_alumno", args=[item.alumno_id]),
            }
            for item in pendientes[:10]
        ],
        "pendientes_count": len(pendientes),
        "prom_resolucion": promedio,
    }


def calcular_actividad_reciente(periodo, fecha, filtros_act):
    """
    Recopila y filtra el feed de eventos de actividad reciente según:
    - actor (sistema vs funcionario o funcionario_id)
    - curso / nivel
    - alumno
    - tipo múltiple (asistencia, justificacion, retiro, alerta)
    """
    tipos = set(filtros_act.get("tipos") or [])
    actor = filtros_act.get("actor")
    curso_id = filtros_act.get("curso")

    alumno_ids_curso = None
    if periodo:
        alumno_ids_curso = obtener_alumnos_ids_activos(
            periodo.pk,
            fecha,
            curso_id=curso_id,
        )

    eventos = []
    ahora = timezone.now()

    # 1. ALERTAS EMITIDAS
    incluir_alertas = (not tipos or "alerta" in tipos) and (actor != "sistema")
    if incluir_alertas:
        qs_alertas = Alerta.objects.filter(fecha__date__lte=fecha).select_related(
            "alumno", "estado", "funcionario", "funcionario__cargo", "periodo"
        )
        if periodo:
            qs_alertas = qs_alertas.filter(periodo_id=periodo.pk)
        if alumno_ids_curso is not None:
            qs_alertas = qs_alertas.filter(alumno_id__in=alumno_ids_curso)

        for alerta in qs_alertas.order_by("-fecha", "-id")[:20]:
            matricula = _curso_alumno(alerta.alumno, alerta.periodo_id, fecha)
            curso = matricula.curso if matricula else None

            # Validar consistencia de curso/nivel si vino filtro
            if curso_id and (not curso or curso.pk != curso_id):
                continue
            eventos.append({
                "fecha": alerta.fecha,
                "tipo": "alerta.emitida",
                "tipo_categoria": "alerta",
                "nivel": alerta.estado.nombre.lower() if alerta.estado else "alerta",
                "alumno": alerta.alumno.nombre,
                "curso": f"{curso.nivel_romano}° Medio {curso.grupo}" if curso else "Sin curso",
                "motivo": "bajo porcentaje de asistencia",
                "autor": alerta.funcionario.nombre if alerta.funcionario else "Funcionario",
                "rol_autor": alerta.funcionario.cargo.nombre if alerta.funcionario and alerta.funcionario.cargo else "Inspectoría",
                "tiempo": _tiempo_transcurrido(alerta.fecha, ahora),
            })

    # 2. JUSTIFICACIONES Y RETIROS
    incluir_just = not tipos or "justificacion" in tipos
    incluir_ret = not tipos or "retiro" in tipos
    if incluir_just or incluir_ret:
        qs_just = Justificaciones.objects.filter(fecha_registro__date__lte=fecha).select_related(
            "alumno", "estado_solicitud", "funcionario_resuelve", "funcionario_resuelve__cargo"
        )
        if incluir_just and not incluir_ret:
            qs_just = qs_just.filter(tipo=Justificaciones.TIPO_JUSTIFICACION)
        elif incluir_ret and not incluir_just:
            qs_just = qs_just.filter(tipo=Justificaciones.TIPO_RETIRO)

        if alumno_ids_curso is not None:
            qs_just = qs_just.filter(alumno_id__in=alumno_ids_curso)

        for justificacion in qs_just.order_by("-fecha_registro", "-id")[:25]:
            matricula = _curso_alumno(
                justificacion.alumno,
                periodo.pk if periodo else None,
                fecha,
            )
            curso = matricula.curso if matricula else None

            if curso_id and (not curso or curso.pk != curso_id):
                continue
            tipo_reg = _tipo_justificacion(justificacion.tipo)
            nombre_reg = "retiro" if tipo_reg == "retiro" else "justificación"

            # Evento A: Registro nuevo (autor = Sistema)
            puede_mostrar_sistema = actor in {None, "sistema"}
            if puede_mostrar_sistema:
                eventos.append({
                    "fecha": justificacion.fecha_registro,
                    "tipo": f"{tipo_reg}.nuevo",
                    "tipo_categoria": tipo_reg,
                    "alumno": justificacion.alumno.nombre,
                    "curso": f"{curso.nivel_romano}° Medio {curso.grupo}" if curso else "Sin curso",
                    "autor": "Sistema",
                    "rol_autor": "Registro recibido",
                    "nombre_registro": nombre_reg,
                    "tiempo": _tiempo_transcurrido(justificacion.fecha_registro, ahora),
                })

            # Evento B: Resolución (autor = Funcionario)
            estado = _nombre_normalizado(justificacion.estado_solicitud.nombre if justificacion.estado_solicitud else "")
            if justificacion.fecha_resolucion and estado in {"aceptada", "rechazada"}:
                f_resuelve = justificacion.funcionario_resuelve
                puede_mostrar_func = (actor != "sistema")

                if puede_mostrar_func:
                    eventos.append({
                        "fecha": justificacion.fecha_resolucion,
                        "tipo": f"{tipo_reg}.{estado}",
                        "tipo_categoria": tipo_reg,
                        "alumno": justificacion.alumno.nombre,
                        "curso": f"{curso.nivel_romano}° Medio {curso.grupo}" if curso else "Sin curso",
                        "autor": f_resuelve.nombre if f_resuelve else "Funcionario",
                        "rol_autor": f_resuelve.cargo.nombre if f_resuelve and f_resuelve.cargo else "Resolución registrada",
                        "nombre_registro": nombre_reg,
                        "tiempo": _tiempo_transcurrido(justificacion.fecha_resolucion, ahora),
                    })

    # 3. REGISTRO DE ASISTENCIA (Paso de Lista)
    incluir_asist = (not tipos or "asistencia" in tipos) and actor != "sistema"
    if incluir_asist:
        qs_pasos = Paso_Lista.objects.filter(fecha__lte=fecha).select_related(
            "curso", "funcionario", "funcionario__cargo"
        )
        if periodo:
            qs_pasos = qs_pasos.filter(curso__periodo_id=periodo.pk)
        if curso_id:
            qs_pasos = qs_pasos.filter(curso_id=curso_id)

        for paso in qs_pasos.order_by("-hora_registro", "-id")[:20]:
            eventos.append({
                "fecha": paso.hora_registro,
                "tipo": "asistencia.registrada",
                "tipo_categoria": "asistencia",
                "curso": f"{paso.curso.nivel_romano}° Medio {paso.curso.grupo}" if paso.curso else "Sin curso",
                "autor": paso.funcionario.nombre if paso.funcionario else "Funcionario",
                "rol_autor": paso.funcionario.cargo.nombre if paso.funcionario and paso.funcionario.cargo else "Docente",
                "tiempo": _tiempo_transcurrido(paso.hora_registro, ahora),
            })

    return sorted(eventos, key=lambda evento: evento["fecha"], reverse=True)[:15]


# =========================================================================
# CATÁLOGOS Y ESTADO DE FILTROS PARA EL FRONTEND
# =========================================================================

def obtener_opciones_filtros(
    periodo_id,
    fecha,
    filtros_ag=None,
    filtros_evo=None,
    filtros_apn=None,
    filtros_ten=None,
    filtros_just=None,
    filtros_act=None,
):
    """
    Retorna los catálogos de opciones y los filtros activos para cada dashboard.
    """
    filtros_ag = filtros_ag or {}
    filtros_evo = filtros_evo or {}
    filtros_apn = filtros_apn or {}
    filtros_ten = filtros_ten or {}
    filtros_just = filtros_just or {}
    filtros_act = filtros_act or {}

    cursos = list(obtener_cursos_disponibles(periodo_id)) if periodo_id else []
    cursos_data = [
        {
            "id": c.pk,
            "nombre": f"{c.nivel_romano}° Medio {c.grupo}",
            "nivel": c.nivel,
            "grupo": c.grupo,
        }
        for c in cursos
    ]

    niveles_data = [
        {"valor": 1, "nombre": "I° Medio"},
        {"valor": 2, "nombre": "II° Medio"},
        {"valor": 3, "nombre": "III° Medio"},
        {"valor": 4, "nombre": "IV° Medio"},
    ]

    mes_max = fecha.month
    meses_data = [
        {"valor": m, "nombre": MESES_COMPLETOS[m - 1], "abreviatura": MESES[m - 1]}
        for m in range(1, mes_max + 1)
    ]

    tipos_actividad = [
        {"valor": "asistencia", "nombre": "Registro de asistencia"},
        {"valor": "justificacion", "nombre": "Justificación"},
        {"valor": "retiro", "nombre": "Retiro"},
        {"valor": "alerta", "nombre": "Alerta"},
    ]

    actores_actividad = [
        {"valor": "sistema", "nombre": "Sistema"},
        {"valor": "funcionario", "nombre": "Funcionario"},
    ]

    return {
        "cursos": cursos_data,
        "niveles": niveles_data,
        "meses": meses_data,
        "tipos_actividad": tipos_actividad,
        "actores_actividad": actores_actividad,
        "activos": {
            "ag": filtros_ag,
            "evo": filtros_evo,
            "apn": filtros_apn,
            "ten": filtros_ten,
            "just": filtros_just,
            "act": filtros_act,
        },
    }
