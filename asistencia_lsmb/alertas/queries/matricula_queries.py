"""Matrículas activas."""
from django.db.models import Q
from django.utils import timezone

from academico.models import Matricula


def matriculas_activas(hoy=None):
    """Matrículas con fecha_termino nula o posterior a `hoy` (por defecto timezone.localdate()).

    Una matrícula que termina hoy ya no es activa. No se mira fecha_matricula.
    """
    hoy = hoy or timezone.localdate()
    return Matricula.objects.filter(Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=hoy))
