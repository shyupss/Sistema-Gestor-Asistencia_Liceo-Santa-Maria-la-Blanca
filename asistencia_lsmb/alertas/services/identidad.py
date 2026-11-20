"""Quién es el funcionario que hace la solicitud.

Mientras no exista el login, el funcionario se toma del setting
FUNCIONARIO_REVISOR_PRUEBA_EMAIL. Este es el único punto que se reemplazará
cuando exista el login.
"""
from django.conf import settings

from alertas.models import Funcionario


def funcionario_actual(request):
    """Funcionario cuyo correo es FUNCIONARIO_REVISOR_PRUEBA_EMAIL (sin distinguir mayúsculas).

    None si el setting está vacío o ningún funcionario tiene ese correo.
    `request` no se usa todavía: lo usará el login.
    """
    correo = (settings.FUNCIONARIO_REVISOR_PRUEBA_EMAIL or "").strip()
    if not correo:
        return None
    return Funcionario.objects.filter(email__iexact=correo).first()
