from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

def pagina_reportes(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Reportes",
        "fecha_hoy": fecha_hoy
    }
    return render(request, "reportes/base.html", contexto)