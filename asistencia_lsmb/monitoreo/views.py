from django.shortcuts import render
from django.utils import timezone
from monitoreo.services.monitoreo_service import preparar_dashboard

def pagina_monitoreo(request):
    fecha_hoy = timezone.localdate()

    # TODO: Borrar info hardcodeada
    justificaciones_pendientes = [
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "1h",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "2h",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "2h 30m",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "5h",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "9h 12m",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "1d",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "2d",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "2d",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "3d",
            "url": "#",
        },
        {
            "alumno": "Nombre Alumno",
            "motivo": "Cita al médico",
            "tiempo": "5d",
            "url": "#",
        },
    ]

    contexto = {
        "page_title": "Monitoreo",
        "fecha_hoy": fecha_hoy,
        **preparar_dashboard(fecha_hoy),

        # TODO: Cambiar info por real
        # JUSTIFICACIONES
        "justificaciones_pendientes": justificaciones_pendientes,
        "pendientes_count": len(justificaciones_pendientes),
        "prom_resolucion": "1.8 días",

        # ACTIVIDAD RECIENTE
        "actividad_reciente": [
            {
                "tipo": "",
                
            }
        ],
    }
    return render(request, "monitoreo/base.html", contexto)