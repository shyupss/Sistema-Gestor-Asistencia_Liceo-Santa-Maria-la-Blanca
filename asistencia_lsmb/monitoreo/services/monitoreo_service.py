import unicodedata
from datetime import date

from django.utils import timezone
from django.urls import reverse

from monitoreo.queries.monitoreo_queries import (
    contar_asistencias,
    contar_matriculas_activas,
    obtener_alertas,
    obtener_alertas_recientes,
    obtener_asistencias_periodo,
    obtener_cursos_periodo,
    obtener_estados_alumnos,
    obtener_historial_alertas,
    obtener_justificaciones_pendientes,
    obtener_justificaciones_recientes,
    obtener_justificaciones_resueltas,
    obtener_periodo_actual,
    obtener_pasos_recientes,
    obtener_pasos_periodo,
)


MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def _porcentaje(total, ausencias):
    return round((total - ausencias) * 100 / total) if total else 0


def _nombre_normalizado(valor):
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", valor.lower())
        if unicodedata.category(caracter) != "Mn"
    )


def _nivel_alerta(nombre):
    nombre = _nombre_normalizado(nombre)
    if "critico" in nombre:
        return "critico"
    if "atencion" in nombre or "alerta" in nombre:
        return "atencion"
    return "atencion"


def _rango_periodo(periodo, fecha):
    inicio = max(periodo.fecha_inicio, date(fecha.year, periodo.fecha_inicio.month, 1))
    fin = min(periodo.fecha_fin, fecha)
    return inicio, fin


def _tiempo_transcurrido(fecha, ahora=None):
    ahora = ahora or timezone.now()
    diferencia = max(ahora - fecha, timezone.timedelta())
    dias = diferencia.days
    horas = diferencia.seconds // 3600
    minutos = (diferencia.seconds % 3600) // 60
    if dias:
        return f"{dias}d" if not horas else f"{dias}d {horas}h"
    if horas:
        return f"{horas}h" if not minutos else f"{horas}h {minutos}m"
    return f"{minutos}m"


def _curso_alumno(alumno, periodo_id=None):
    matriculas = alumno.matriculas.select_related("curso")
    if periodo_id:
        matriculas = matriculas.filter(periodo_id=periodo_id)
    return matriculas.filter(fecha_termino__isnull=True).first() or matriculas.first()


def preparar_justificaciones(fecha):
    pendientes = list(obtener_justificaciones_pendientes(fecha)[:10])
    resueltas = list(obtener_justificaciones_resueltas(fecha))
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
            for item in pendientes
        ],
        "pendientes_count": len(pendientes),
        "prom_resolucion": promedio,
    }


def preparar_actividad_reciente(fecha):
    eventos = []
    ahora = timezone.now()

    for alerta in obtener_alertas_recientes(fecha):
        matricula = _curso_alumno(alerta.alumno, alerta.periodo_id)
        curso = matricula.curso if matricula else None
        eventos.append({
            "fecha": alerta.fecha,
            "tipo": "alerta.emitida",
            "nivel": alerta.estado.nombre.lower(),
            "alumno": alerta.alumno.nombre,
            "curso": f"{curso.nivel_romano}° Medio {curso.grupo}" if curso else "Sin curso",
            "motivo": "bajo porcentaje de asistencia",
            "autor": alerta.funcionario.nombre,
            "rol_autor": alerta.funcionario.cargo.nombre,
            "tiempo": _tiempo_transcurrido(alerta.fecha, ahora),
        })

    for justificacion in obtener_justificaciones_recientes(fecha):
        matricula = _curso_alumno(justificacion.alumno)
        curso = matricula.curso if matricula else None
        funcionario = justificacion.funcionario_resuelve
        eventos.append({
            "fecha": justificacion.fecha_registro,
            "tipo": "justificacion.nueva",
            "alumno": justificacion.alumno.nombre,
            "curso": f"{curso.nivel_romano}° Medio {curso.grupo}" if curso else "Sin curso",
            "autor": funcionario.nombre if funcionario else "Sistema",
            "rol_autor": funcionario.cargo.nombre if funcionario else None,
            "tiempo": _tiempo_transcurrido(justificacion.fecha_registro, ahora),
        })

    for paso in obtener_pasos_recientes(fecha):
        eventos.append({
            "fecha": paso.hora_registro,
            "tipo": "asistencia.registrada",
            "curso": f"{paso.curso.nivel_romano}° Medio {paso.curso.grupo}",
            "autor": paso.funcionario.nombre,
            "rol_autor": paso.funcionario.cargo.nombre,
            "tiempo": _tiempo_transcurrido(paso.hora_registro, ahora),
        })

    return sorted(eventos, key=lambda evento: evento["fecha"], reverse=True)[:10]


def _datos_asistencia(periodo, cursos, fecha):
    inicio, fin = _rango_periodo(periodo, fecha)
    asistencias = obtener_asistencias_periodo(periodo.pk, fin).filter(
        paso_lista__fecha__gte=inicio,
    )
    total, ausencias = contar_asistencias(asistencias)
    meses = list(range(inicio.month, fin.month + 1)) if inicio <= fin else []
    evolucion = []
    for mes in meses:
        registros_mes = asistencias.filter(paso_lista__fecha__month=mes)
        total_mes, ausencias_mes = contar_asistencias(registros_mes)
        evolucion.append({
            "mes": MESES[mes - 1],
            "valor": _porcentaje(total_mes, ausencias_mes),
        })

    asistencia_por_curso = []
    for curso in cursos:
        registros_curso = asistencias.filter(paso_lista__curso=curso)
        total_curso, ausencias_curso = contar_asistencias(registros_curso)
        asistencia_por_curso.append({
            "curso": f"{curso.nivel_romano}°{curso.grupo}",
            "porcentaje": _porcentaje(total_curso, ausencias_curso) if total_curso else None,
        })

    pasos_hoy = obtener_pasos_periodo(periodo.pk, fecha).filter(fecha=fecha)
    cursos_pendientes = [
        {
            "nombre": f"{curso.nivel_romano}° medio {curso.grupo}",
            "url": f"{reverse('registrar_asistencia')}?curso={curso.pk}&fecha={fecha.isoformat()}",
        }
        for curso in cursos
        if not pasos_hoy.filter(curso=curso).exists()
    ]

    return {
        "asistencia_general": {
            "porcentaje": _porcentaje(total, ausencias),
            "meta": 75,
            "periodo": f"Periodo académico {periodo.anio}",
        },
        "evolucion_asistencia": {
            "labels": [item["mes"] for item in evolucion],
            "valores": [item["valor"] for item in evolucion],
        },
        "asistencia_por_curso": asistencia_por_curso,
        "cursos_disponibles": [
            "Asistencia General",
            *[f"{curso.nivel_romano}°{curso.grupo}" for curso in cursos],
        ],
        "cursos_pendientes": cursos_pendientes,
    }


def _datos_alertas(periodo, cursos, fecha):
    estados = list(obtener_estados_alumnos(periodo.pk))
    estados_alerta = [estado for estado in estados if estado.estado.genera_alerta]
    atencion = sum(_nivel_alerta(estado.estado.nombre) == "atencion" for estado in estados_alerta)
    critico = sum(_nivel_alerta(estado.estado.nombre) == "critico" for estado in estados_alerta)
    total = atencion + critico

    ranking = []
    matriculas = {}
    for curso in cursos:
        matriculas.update({
            matricula.alumno_id: curso
            for matricula in curso.matriculas.all()
            if matricula.fecha_termino is None or matricula.fecha_termino > fecha
        })
    for estado in sorted(
        estados_alerta,
        key=lambda item: (_nivel_alerta(item.estado.nombre) != "critico", item.porcentaje_asistencia),
    )[:5]:
        curso = matriculas.get(estado.alumno_id)
        if not curso:
            continue
        nivel = _nivel_alerta(estado.estado.nombre)
        ranking.append({
            "posicion": len(ranking) + 1,
            "alumno": estado.alumno.nombre,
            "curso": f"{curso.nivel_romano}° Medio {curso.grupo}",
            "atencion": int(nivel == "atencion"),
            "critico": int(nivel == "critico"),
            "url": reverse("perfil_alumno", args=[estado.alumno_id]),
        })

    alertas_por_curso = []
    for curso in cursos:
        alumno_ids = {
            estado.alumno_id
            for estado in estados_alerta
            if estado.alumno_id in {
                matricula.alumno_id for matricula in curso.matriculas.all()
                if matricula.fecha_termino is None or matricula.fecha_termino > fecha
            }
        }
        alertas_por_curso.append({
            "curso": f"{curso.nivel_romano}°{curso.grupo}",
            "valor": len(alumno_ids),
        })

    historial = obtener_historial_alertas(periodo.pk, fecha)
    tendencia = []
    inicio, fin = _rango_periodo(periodo, fecha)
    for mes in range(inicio.month, fin.month + 1) if inicio <= fin else []:
        tendencia.append({
            "mes": MESES[mes - 1],
            "valor": historial.filter(fecha_cambio__month=mes).count(),
        })

    alertas = obtener_alertas(periodo.pk, fecha)[:10]
    alertas_recientes = []
    for alerta in alertas:
        curso = matriculas.get(alerta.alumno_id)
        if curso:
            alertas_recientes.append({
                "alumno": alerta.alumno.nombre,
                "curso": f"{curso.nivel_romano}° Medio {curso.grupo}",
                "hace": alerta.fecha.strftime("%d/%m/%Y"),
                "nivel": _nivel_alerta(alerta.estado.nombre),
            })

    return {
        "alertas_por_nivel": {
            "atencion": atencion,
            "critico": critico,
            "total": total,
            "pct_atencion": round(atencion * 100 / total) if total else 0,
            "pct_critico": round(critico * 100 / total) if total else 0,
        },
        "alertas_por_curso": {
            "labels": [item["curso"] for item in alertas_por_curso],
            "valores": [item["valor"] for item in alertas_por_curso],
        },
        "tendencia_alertas": {
            "labels": [item["mes"] for item in tendencia],
            "valores": [item["valor"] for item in tendencia],
        },
        "ranking_alertas": ranking,
        "ranking_ver_todos_url": reverse("alertas"),
        "alertas_recientes": alertas_recientes,
    }


def preparar_dashboard(fecha):
    periodo_id = obtener_periodo_actual(fecha)
    if not periodo_id:
        return {
            "asistencia_general": {"porcentaje": 0, "meta": 75, "periodo": "Sin periodo académico"},
            "evolucion_asistencia": {"labels": [], "valores": []},
            "asistencia_por_curso": [],
            "cursos_disponibles": ["Asistencia General"],
            "cursos_pendientes": [],
            "alertas_por_nivel": {"atencion": 0, "critico": 0, "total": 0, "pct_atencion": 0, "pct_critico": 0},
            "alertas_por_curso": {"labels": [], "valores": []},
            "tendencia_alertas": {"labels": [], "valores": []},
            "ranking_alertas": [],
            "ranking_ver_todos_url": reverse("alertas"),
            "alertas_recientes": [],
        }

    periodo = obtener_cursos_periodo(periodo_id).first().periodo
    cursos = list(obtener_cursos_periodo(periodo_id))
    return {
        **_datos_asistencia(periodo, cursos, fecha),
        **_datos_alertas(periodo, cursos, fecha),
    }