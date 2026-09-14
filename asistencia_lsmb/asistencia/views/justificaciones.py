from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

def pagina_justificaciones(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Justificaciones",
        "fecha_hoy": fecha_hoy
    }
    return render(request, "justificaciones/base.html", contexto)