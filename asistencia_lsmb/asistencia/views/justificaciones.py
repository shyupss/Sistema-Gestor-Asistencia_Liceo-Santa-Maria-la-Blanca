from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q

from babel.dates import format_date
from asistencia.models import Justificaciones

def pagina_justificaciones(request):
    fecha_hoy = timezone.localdate()
    filtro_actual = request.GET.get('estado')
    busqueda = request.GET.get('q', '')

    justificaciones = Justificaciones.objects.select_related(
        'alumno', 'estado_solicitud'
    )

    if filtro_actual:
        justificaciones = justificaciones.filter(
            estado_solicitud__nombre__iexact = filtro_actual
        )

    if busqueda:
        justificaciones = justificaciones.filter(
            Q(alumno__nombre__icontains = busqueda) |
            Q(alumno__rut__icontains = busqueda)
        )

    contexto = {
        "page_title": "Justificaciones",
        "fecha_hoy": fecha_hoy,
        "justificaciones": justificaciones,
        "filtro_actual": filtro_actual,
        "busqueda": busqueda,
        "pendientes_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'pendientes').count(),
        "aceptadas_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'aceptadas').count(),
        "rechazadas_count": Justificaciones.objects.filter(estado_solicitud__nombre__iexact = 'rechazadas').count(),
    }
    return render(request, "justificaciones/base.html", contexto)