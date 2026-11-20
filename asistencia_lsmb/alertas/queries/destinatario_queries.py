"""Destinatarios del correo de alertas y los estados que recibe cada rol."""
from django.db.models import Exists, OuterRef

from alertas.models import EstadoNotificaRol, Funcionario, RolPermiso


def funcionarios_con_permiso(codigo):
    """Funcionarios activos con cuenta activa cuyo rol tiene el permiso `codigo`, por id.

    Mismo criterio que alcance_queries.tiene_permiso. Trae la cuenta y su rol con
    select_related para no consultar por fila. El permiso se verifica con
    EXISTS, así que no hay duplicados.
    """
    rol_con_permiso = RolPermiso.objects.filter(rol=OuterRef("cuenta__rol"), permiso__codigo=codigo)
    return (
        Funcionario.objects.filter(activo=True, cuenta__activo=True)
        .filter(Exists(rol_con_permiso))
        .select_related("cuenta__rol")
        .order_by("pk")
    )


def estados_que_notifica_el_rol(rol):
    """Ids de los Estado que el rol (instancia o id) tiene en EstadoNotificaRol, ordenados.

    Una lista vacía significa que el rol no recibe ningún estado, nunca "todos".
    """
    return list(
        EstadoNotificaRol.objects.filter(rol=rol)
        .order_by("estado_id")
        .values_list("estado_id", flat=True)
    )
