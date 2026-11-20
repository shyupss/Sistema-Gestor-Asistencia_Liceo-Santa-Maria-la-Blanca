from django.db.models import Min

from alertas.models import Estado


def umbral_critico():
    """Umbral mínimo del catálogo de estados no ideales (None si no hay ninguno).

    Debe calcularse desde el catálogo completo de Estado, no desde los alumnos
    presentes: si solo hubiera alumnos en un estado intermedio, se
    etiquetarían como críticos por error.
    """
    return Estado.objects.filter(es_no_ideal=True).aggregate(
        minimo=Min("umbral_minimo")
    )["minimo"]


def nivel_alerta(estado, umbral_critico):
    """Clasifica un Estado en 'critico' o 'atencion' por orden de umbral.

    'critico' es el estado no ideal con el menor umbral_minimo del catálogo
    (si es el único no ideal, también es 'critico'); los demás son 'atencion'.
    Solo debe llamarse con estados que tienen es_no_ideal=True. Si
    umbral_critico es None (no hay estados no ideales) devuelve 'atencion'.
    """
    if umbral_critico is not None and estado.umbral_minimo <= umbral_critico:
        return "critico"
    return "atencion"
