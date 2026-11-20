"""Alcance de un funcionario: qué permisos tiene y qué cursos ve.

Solo dependen de Rol.alcance, de RolPermiso y del código de permiso recibido;
nunca de nombres de roles ni de estados. Un funcionario tiene acceso solo si
está activo y tiene una cuenta activa.
"""
from django.db.models import Q

from academico.models import Curso, Matricula
from alertas.models import Cuenta, FuncionarioCurso, Rol


def _cuentas_con_acceso(funcionario):
    return Cuenta.objects.filter(funcionario=funcionario, activo=True, funcionario__activo=True)


def tiene_permiso(funcionario, codigo):
    """True si el funcionario tiene acceso y el rol de su cuenta tiene el permiso `codigo`."""
    return _cuentas_con_acceso(funcionario).filter(
        rol__permisos_asignados__permiso__codigo=codigo,
    ).exists()


def cursos_en_alcance(funcionario, periodo):
    """Cursos del período (instancia o id) que ve el funcionario, como QuerySet.

    - Sin acceso (funcionario inactivo o sin cuenta activa): ninguno.
    - Alcance "todos": todos los cursos del período.
    - Alcance "seleccionados": los asignados en FuncionarioCurso más aquellos
      donde es Curso.profesor_jefe, sin duplicados.
    """
    cursos = Curso.objects.filter(periodo=periodo)
    cuenta = _cuentas_con_acceso(funcionario).select_related("rol").first()
    if cuenta is None:
        return cursos.none()
    if cuenta.rol.alcance == Rol.ALCANCE_TODOS:
        return cursos
    # Subconsulta en vez de JOIN: no duplica filas, así que no hace falta
    # distinct() y el QuerySet se puede seguir filtrando o agregando.
    asignados = FuncionarioCurso.objects.filter(funcionario=funcionario).values("curso_id")
    return cursos.filter(Q(pk__in=asignados) | Q(profesor_jefe=funcionario))


def curso_del_alumno_en_periodo(alumno, periodo, hoy):
    """Curso del alumno en el período (instancia o id), o None si no tiene matrícula en él.

    Usa la matrícula activa (fecha_termino nula o posterior a `hoy`). Si no hay
    ninguna (p. ej. el barrido aún no cerró la alerta), usa la más reciente del
    período. Entre varias, gana la de mayor fecha_matricula y luego la de mayor id.
    """
    matriculas = (
        Matricula.objects.filter(alumno=alumno, periodo=periodo)
        .select_related("curso")
        .order_by("-fecha_matricula", "-pk")
    )
    matricula = (
        matriculas.filter(Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=hoy)).first()
        or matriculas.first()
    )
    return matricula.curso if matricula else None
