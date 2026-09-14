from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

def pagina_monitoreo(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Monitoreo",
        "fecha_hoy": fecha_hoy
    }
    return render(request, "monitoreo/base.html", contexto)