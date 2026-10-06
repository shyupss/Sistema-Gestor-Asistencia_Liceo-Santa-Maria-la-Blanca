from django.db import transaction
from django.db.models import Q

from academico.models import Alumno, PeriodoAcademico
from asistencia.models import Asistencia_Alumnos, Estados_Solicitud, Justificaciones, Tipos_Asistencia
from asistencia.services.asistencia_service import recalcular_estado_alumno


TIPOS_ASISTENCIA = {
    "presente": False,
    "ausente": True,
    "atrasado": True,
    "justificado": False,
}
ESTADOS_SOLICITUD = {
    "pendiente": (False, False, "Solicitud pendiente de revisión."),
    "aceptada": (True, True, "Solicitud aceptada; cubre la ausencia."),
    "rechazada": (True, False, "Solicitud rechazada; no cubre la ausencia."),
}


def _guardar(modelo, nombre, valores, descripcion=None):
    defaults = dict(valores)
    if descripcion is not None:
        defaults["descripcion"] = descripcion
    registro, creado = modelo.objects.get_or_create(
        nombre__iexact=nombre, defaults={"nombre": nombre, **defaults},
    )
    cambio_reglas = not creado and any(
        getattr(registro, campo) != valor for campo, valor in valores.items()
    )
    cambios = {campo: valor for campo, valor in {"nombre": nombre, **valores}.items()
               if getattr(registro, campo) != valor}
    if cambios:
        for campo, valor in cambios.items():
            setattr(registro, campo, valor)
        registro.save(update_fields=list(cambios))
    return registro, creado, bool(cambios), cambio_reglas


@transaction.atomic
def cargar_catalogos_asistencia():
    """Crea o actualiza los catálogos sin reemplazar sus IDs ni relaciones."""
    creados = 0
    ids_actualizados = set()
    tipos_modificados = []
    estados_modificados = []
    # Reparar el nombre utilizado en la carga anterior, conservando las relaciones.
    try:
        anterior = Estados_Solicitud.objects.get(nombre__iexact="aprobada")
    except Estados_Solicitud.DoesNotExist:
        anterior = None
    if anterior and not Estados_Solicitud.objects.filter(nombre__iexact="aceptada").exists():
        anterior.nombre = "aceptada"
        if anterior.descripcion == "Solicitud aprobada; cubre la ausencia.":
            anterior.descripcion = "Solicitud aceptada; cubre la ausencia."
        anterior.save(update_fields=["nombre", "descripcion"])
        ids_actualizados.add(anterior.pk)
        anterior = None
    for nombre, ausencia in TIPOS_ASISTENCIA.items():
        registro, creado, actualizado, cambio_reglas = _guardar(
            Tipos_Asistencia, nombre, {"cuenta_como_ausencia": ausencia},
        )
        creados += creado
        if actualizado:
            ids_actualizados.add(registro.pk)
        if cambio_reglas:
            tipos_modificados.append(registro.pk)
    for nombre, (final, cubre, descripcion) in ESTADOS_SOLICITUD.items():
        registro, creado, actualizado, cambio_reglas = _guardar(
            Estados_Solicitud, nombre,
            {"es_estado_final": final, "cubre_ausencia": cubre}, descripcion,
        )
        creados += creado
        if actualizado:
            ids_actualizados.add(registro.pk)
        if cambio_reglas:
            estados_modificados.append(registro.pk)

    if anterior:
        aceptada = Estados_Solicitud.objects.get(nombre__iexact="aceptada")
        Justificaciones.objects.filter(estado_solicitud=anterior).update(estado_solicitud=aceptada)
        anterior.delete()
        estados_modificados.append(aceptada.pk)
        ids_actualizados.add(aceptada.pk)

    # Una corrección de las reglas también debe actualizar los porcentajes guardados.
    if tipos_modificados or estados_modificados:
        afectados = Asistencia_Alumnos.objects.filter(
            Q(tipo_asistencia_id__in=tipos_modificados)
            | Q(justificacion__estado_solicitud_id__in=estados_modificados)
        ).values_list("alumno_id", "paso_lista__curso__periodo_id").distinct()
        for alumno_id, periodo_id in afectados:
            recalcular_estado_alumno(
                Alumno.objects.get(pk=alumno_id),
                PeriodoAcademico.objects.get(pk=periodo_id),
            )
    return creados, len(ids_actualizados)
