from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from babel.dates import format_datetime, format_date

from asistencia.models import Estados_Solicitud, Justificaciones

def pagina_justificaciones_ficha(request):
    id_justificacion = request.GET.get('id')
    justificacion = get_object_or_404(
        Justificaciones.objects.select_related(
            'alumno', 'estado_solicitud', 'funcionario_resuelve'
        ).prefetch_related('adjuntos'),
        pk=id_justificacion,
    )

    if request.method == 'POST':
        accion = request.POST.get('accion')
        nombre_estado = {
            'aceptar': 'aceptada',
            'rechazar': 'rechazada',
        }.get(accion)

        if nombre_estado and not justificacion.estado_solicitud.es_estado_final:
            estado = get_object_or_404(Estados_Solicitud, nombre__iexact=nombre_estado)
            justificacion.estado_solicitud = estado
            justificacion.fecha_resolucion = timezone.now()
            justificacion.save(update_fields=['estado_solicitud', 'fecha_resolucion'])
            messages.success(request, f'La justificación fue {nombre_estado}.')
        else:
            messages.error(request, 'La acción solicitada no es válida.')

        volver_url = request.POST.get('next') or reverse('justificaciones')
        return redirect(volver_url)

    matricula = justificacion.alumno.matriculas.select_related('curso').order_by('-fecha_matricula').first()

    bitacora = [
        {
            'tipo': 'creacion',
            'fecha': justificacion.fecha_registro,
        },
    ]
    if justificacion.fecha_resolucion:
        bitacora.append({
            'tipo': 'revision',
            'autor': justificacion.funcionario_resuelve.nombre if justificacion.funcionario_resuelve else None,
            'fecha': justificacion.fecha_resolucion,
        })
    bitacora.append({
        'tipo': 'actual',
        'estado': justificacion.estado_solicitud.nombre,
    })

    volver_url = request.GET.get('next') or reverse('justificaciones')
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "inicio" 

    contexto = {
        'page_title': 'Justificación' if justificacion.tipo == 'justificacion' else 'Retiro',
        'volver_url': volver_url,
        'volver_label': volver_label,

        'nombre': justificacion.alumno.nombre,
        'rut': justificacion.alumno.rut,
        'curso': matricula.curso if matricula else None,
        'estado': justificacion.estado_solicitud.nombre,
        'tipo': justificacion.tipo,
        'pendiente': not justificacion.estado_solicitud.es_estado_final,
        'periodo': '{} al {}'.format(
            format_date(justificacion.fecha_inicio, 'd MMMM yyyy', locale='es_CL'),
            format_date(justificacion.fecha_fin, 'd MMMM yyyy', locale='es_CL'),
        ),
        'registro': format_datetime(justificacion.fecha_registro, 'd/MM/yyyy, HH:mm', locale='es_CL'),
        'resumen': justificacion.resumen,
        'detalle': justificacion.motivo,
        'documentos': [
            {'nombre': adjunto.nombre_original, 'url': adjunto.archivo.url}
            for adjunto in justificacion.adjuntos.all()
        ],
        'bitacora': bitacora,
    }
    return render(request, 'justificaciones/ficha.html', contexto)