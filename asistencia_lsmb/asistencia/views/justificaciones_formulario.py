from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.http import Http404
from django.utils.dateparse import parse_date
from django.db.models import Prefetch, Q

from academico.models import Alumno, Matricula
from asistencia.models import Adjunto_Justificacion, Estados_Solicitud, Justificaciones

TIPOS_VALIDOS = { 'justificacion', 'retiro' }

def pagina_justificaciones_formulario(request):
    tipo = request.GET.get('tipo')
    busqueda_estudiante = ''
    estudiante_contexto = None

    if tipo not in TIPOS_VALIDOS:
        raise Http404("Tipo de formulario no válido")

    volver_url = request.GET.get('next') or reverse('justificaciones')
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "inicio" 

    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        volver_url = request.POST.get('next') or reverse('justificaciones')
        busqueda = request.POST.get('busqueda_estudiante', '').strip()
        busqueda_estudiante = busqueda
        fecha_inicio = parse_date(request.POST.get('fecha_inicio', ''))
        fecha_fin = parse_date(request.POST.get('fecha_fin', ''))
        resumen = request.POST.get('resumen', '').strip()
        detalle = request.POST.get('detalle', '').strip()

        errores = []
        estudiantes = Alumno.objects.prefetch_related(
            Prefetch(
                'matriculas',
                queryset=Matricula.objects.select_related('curso').order_by('-fecha_matricula'),
                to_attr='matriculas_formulario',
            ),
            'apoderados',
        ).filter(
            Q(rut__iexact=busqueda) | Q(nombre__iexact=busqueda)
        )
        if not estudiantes.exists() and busqueda:
            estudiantes = Alumno.objects.filter(nombre__icontains=busqueda)

        if estudiantes.count() != 1:
            errores.append('Selecciona un único estudiante válido por nombre o RUT.')
        else:
            estudiante = estudiantes.first()
            matriculas = estudiante.matriculas_formulario
            estudiante_contexto = {
                'alumno': estudiante,
                'curso': matriculas[0].curso if matriculas else None,
                'apoderado': estudiante.apoderados.first(),
            }
        if not fecha_inicio or not fecha_fin or fecha_fin < fecha_inicio:
            errores.append('El periodo indicado no es válido.')
        if not resumen:
            errores.append('El resumen es obligatorio.')
        if tipo not in TIPOS_VALIDOS:
            errores.append('El tipo de registro no es válido.')

        try:
            estado = Estados_Solicitud.objects.get(nombre__iexact='pendiente')
        except Estados_Solicitud.DoesNotExist:
            estado = None
            errores.append('No existe el estado inicial "pendiente".')

        if not errores:
            with transaction.atomic():
                justificacion = Justificaciones.objects.create(
                    alumno=estudiantes.first(),
                    tipo=tipo,
                    estado_solicitud=estado,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    resumen=resumen,
                    motivo=detalle,
                )
                for archivo in request.FILES.getlist('adjuntos'):
                    Adjunto_Justificacion.objects.create(
                        justificacion=justificacion,
                        archivo=archivo,
                        nombre_original=archivo.name,
                    )
            messages.success(request, 'El registro se creó correctamente.')
            return redirect(volver_url)

        for error in errores:
            messages.error(request, error)

    contexto = {
        'page_title': 'Nueva justificación' if tipo == 'justificacion' else 'Nuevo retiro' if tipo == 'retiro' else 'Nuevo registro',
        'tipo': tipo,
        'volver_url': volver_url,
        'volver_label': volver_label,
        'busqueda_estudiante': busqueda_estudiante,
        'estudiante_contexto': estudiante_contexto,
    }
    return render(request, 'justificaciones/formulario.html', contexto)