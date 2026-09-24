from django.shortcuts import render
from django.utils import timezone
from django.db.models import Prefetch, Q
from datetime import timedelta

from academico.models import Matricula
from asistencia.models import Justificaciones

def pagina_justificaciones(request):
    fecha_hoy = timezone.localdate()
    filtro_actual = request.GET.get('estado')
    busqueda = request.GET.get('q', '').strip()
    rango = request.GET.get('rango', 'Últimos 30 días')
    orden = request.GET.get('orden', 'Recientes primero')

    justificaciones = Justificaciones.objects.select_related(
        'alumno', 'estado_solicitud'
    ).prefetch_related(
        Prefetch(
            'alumno__matriculas',
            queryset=Matricula.objects.select_related('curso').order_by('-fecha_matricula'),
            to_attr='matriculas_justificaciones',
        ),
        Prefetch('adjuntos', to_attr='adjuntos_justificacion'),
    )

    if filtro_actual:
        justificaciones = justificaciones.filter(
            estado_solicitud__nombre__iexact = filtro_actual
        )

    if busqueda:
        justificaciones = justificaciones.filter(
            Q(alumno__nombre__icontains = busqueda) |
            Q(alumno__rut__icontains = busqueda) |
            Q(alumno__matriculas__curso__grupo__icontains = busqueda)
        ).distinct()

    rangos = {
        'Últimos 30 días': fecha_hoy - timedelta(days=29),
        'Últimos 7 días': fecha_hoy - timedelta(days=6),
        'Último mes': fecha_hoy.replace(day=1),
        'Última semana': fecha_hoy - timedelta(days=fecha_hoy.weekday()),
    }
    if rango in rangos:
        justificaciones = justificaciones.filter(
            fecha_registro__date__gte=rangos[rango],
            fecha_registro__date__lte=fecha_hoy,
        )
    else:
        rango = 'Todo'

    if orden == 'Antiguos primero':
        justificaciones = justificaciones.order_by('fecha_registro', 'id')
    else:
        orden = 'Recientes primero'
        justificaciones = justificaciones.order_by('-fecha_registro', '-id')

    total = justificaciones.count()
    tarjetas = []
    for justificacion in justificaciones:
        matriculas = justificacion.alumno.matriculas_justificaciones
        adjuntos = justificacion.adjuntos_justificacion
        matricula = matriculas[0] if matriculas else None
        archivo = adjuntos[0] if adjuntos else None
        tarjetas.append({
            'justificacion': justificacion,
            'curso': matricula.curso if matricula else None,
            'archivo': archivo,
        })

    contexto = {
        "page_title": "Justificaciones",
        "fecha_hoy": fecha_hoy,
        "justificaciones": justificaciones,
        "tarjetas": tarjetas,
        "filtro_actual": filtro_actual,
        "busqueda": busqueda,
        "rango": rango,
        "orden": orden,
        "mostrando": total,
        "total": total,
        "pendientes_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'pendiente').count(),
        "aceptadas_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'aceptada').count(),
        "rechazadas_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'rechazada').count(),
    }
    return render(request, "justificaciones/base.html", contexto)