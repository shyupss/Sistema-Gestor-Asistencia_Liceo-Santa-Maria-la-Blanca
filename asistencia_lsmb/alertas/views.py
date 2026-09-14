from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

def pagina_alertas(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Alertas",
        "fecha_hoy": fecha_hoy
    }
    return render(request, "alertas/base.html", contexto)