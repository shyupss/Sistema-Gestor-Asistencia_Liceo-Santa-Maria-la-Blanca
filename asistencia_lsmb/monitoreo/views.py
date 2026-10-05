from django.shortcuts import render
from django.utils import timezone
from monitoreo.services.monitoreo_service import preparar_dashboard

def pagina_monitoreo(request):
    fecha_hoy = timezone.localdate()
    contexto = {
        "page_title": "Monitoreo",
        "fecha_hoy": fecha_hoy,
        **preparar_dashboard(fecha_hoy),
    }
    return render(request, "monitoreo/base.html", contexto)