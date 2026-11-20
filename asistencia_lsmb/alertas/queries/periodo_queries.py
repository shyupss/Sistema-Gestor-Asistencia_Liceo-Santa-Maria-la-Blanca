"""Período académico vigente."""
from django.utils import timezone

from academico.models import PeriodoAcademico


def periodo_actual(hoy=None):
    """PeriodoAcademico cuyo anio es el año de `hoy` (por defecto timezone.localdate()), o None."""
    hoy = hoy or timezone.localdate()
    return PeriodoAcademico.objects.filter(anio=hoy.year).first()
