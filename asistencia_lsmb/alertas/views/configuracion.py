from django.shortcuts import render
from django.utils import timezone
from django.urls import reverse

def pagina_configuracion(request):
    fecha_hoy = timezone.localdate()

    volver_url = request.POST.get('next') or reverse('alertas')
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "alertas"
    
    contexto = {
        "page_title": "Configuración de alertas",
        "fecha_hoy": fecha_hoy,
        "volver_url": volver_url,
        "volver_label": volver_label,
    }
    return render(request, 'alertas/configuracion.html', context = contexto)