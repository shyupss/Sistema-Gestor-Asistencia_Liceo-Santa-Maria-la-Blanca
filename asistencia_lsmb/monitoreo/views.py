from django.shortcuts import render
from django.utils import timezone
from monitoreo.queries.filtro_queries import obtener_periodo_activo
from monitoreo.services.filtro_service import (
    calcular_actividad_reciente,
    calcular_alertas_por_nivel,
    calcular_asistencia_general,
    calcular_evolucion_asistencia,
    calcular_justificaciones,
    calcular_tendencia_alertas,
    obtener_opciones_filtros,
    resolver_filtros_actividad_reciente,
    resolver_filtros_alertas_nivel,
    resolver_filtros_asistencia_general,
    resolver_filtros_evolucion,
    resolver_filtros_justificaciones,
    resolver_filtros_tendencia_alertas,
)
from monitoreo.services.monitoreo_service import preparar_dashboard


def pagina_monitoreo(request):
    fecha_hoy = timezone.localdate()
    periodo = obtener_periodo_activo(fecha_hoy)

    # 1. Resolver filtros independientes para cada componente
    filtros_ag = resolver_filtros_asistencia_general(request.GET)
    filtros_evo = resolver_filtros_evolucion(request.GET)
    filtros_apn = resolver_filtros_alertas_nivel(request.GET)
    filtros_ten = resolver_filtros_tendencia_alertas(request.GET)
    filtros_just = resolver_filtros_justificaciones(request.GET)
    filtros_act = resolver_filtros_actividad_reciente(request.GET)

    # 2. Calcular datos aplicando los filtros correspondientes
    asistencia_general = calcular_asistencia_general(periodo, fecha_hoy, filtros_ag)
    evolucion_asistencia = calcular_evolucion_asistencia(periodo, fecha_hoy, filtros_evo)
    alertas_por_nivel = calcular_alertas_por_nivel(periodo, fecha_hoy, filtros_apn)
    tendencia_alertas = calcular_tendencia_alertas(periodo, fecha_hoy, filtros_ten)
    justificaciones = calcular_justificaciones(periodo, fecha_hoy, filtros_just)
    actividad_reciente = calcular_actividad_reciente(periodo, fecha_hoy, filtros_act)

    # 3. Catálogos y estado activo para que el frontend pueda renderizar los selectores
    opciones_filtros = obtener_opciones_filtros(
        periodo.pk if periodo else None,
        fecha_hoy,
        filtros_ag=filtros_ag,
        filtros_evo=filtros_evo,
        filtros_apn=filtros_apn,
        filtros_ten=filtros_ten,
        filtros_just=filtros_just,
        filtros_act=filtros_act,
    )

    contexto = {
        "page_title": "Monitoreo",
        "fecha_hoy": fecha_hoy,
        **preparar_dashboard(fecha_hoy),
        **justificaciones,
        "actividad_reciente": actividad_reciente,
        # Sobrescribir con los datos filtrados:
        "asistencia_general": asistencia_general,
        "evolucion_asistencia": evolucion_asistencia,
        "alertas_por_nivel": alertas_por_nivel,
        "tendencia_alertas": tendencia_alertas,
        "filtros_monitoreo": opciones_filtros,
    }
    return render(request, "monitoreo/base.html", contexto)
