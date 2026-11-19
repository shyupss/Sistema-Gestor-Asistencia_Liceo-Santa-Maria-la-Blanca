"""Ambiente de prueba: deja el sistema listo para probar con un solo clic.

En este orden, crea lo que falte:
1. Permisos: revisar_alertas y cuatro ficticios (sin efecto en el código).
2. El período académico del año actual (1 de marzo a 31 de diciembre).
3. Los 12 cursos de ese período: 1° a 4° medio, grupos A, B y C.
4. Roles, cargos y funcionarios de prueba, cada funcionario con su cuenta
   activa. Solo a los roles creados en esta pulsación se les asignan permisos
   y los estados de alerta que los notifican.
5. Dos Inspectores de contraste: uno con el funcionario inactivo y otro con la
   cuenta inactiva.
6. En los cursos creados en esta pulsación: el profesor jefe y los Inspectores.

Solo faltan los alumnos, que se inscriben con la planilla.

Idempotente (una segunda pulsación no crea nada) y atómico. Nunca modifica ni
borra lo existente. Si un RUT de prueba lo usa otro funcionario, cancela todo.
"""
import datetime
import re
import unicodedata
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from academico.models import Curso, PeriodoAcademico
from alertas.models import (
    Cargo,
    Cuenta,
    Estado,
    EstadoNotificaRol,
    Funcionario,
    FuncionarioCurso,
    Permiso,
    Rol,
    RolPermiso,
)

# Buzón de pruebas: los correos de los funcionarios usan subdirección "+"
# (asistencia+rector1@lsmb.cl) y todos llegan a este buzón.
CORREO_BASE = "asistencia@lsmb.cl"
# RUT ficticios y reconocibles: 99000001-0, 99000002-0, ...
RUT_BASE = 99000000
RUT_DV = "0"

FICTICIO = "(ficticio, sin efecto en el código)"
# código -> (nombre, descripción)
PERMISOS = {
    "revisar_alertas": (
        "Revisar alertas", "Permite revisar alertas y recibir notificaciones de alertas.",
    ),
    "ver_monitoreo": ("Ver monitoreo", FICTICIO),
    "gestionar_justificaciones": ("Gestionar justificaciones", FICTICIO),
    "cargar_datos": ("Cargar datos", FICTICIO),
    "configurar_umbrales": ("Configurar umbrales", FICTICIO),
}

NIVELES = (1, 2, 3, 4)
GRUPOS = ("A", "B", "C")
# Curso al que se vinculan los Inspectores de contraste: (nivel, grupo).
CURSO_CONTRASTE = (1, "A")

# Qué estados de alerta notifican a un rol (EstadoNotificaRol).
NOTIFICA_MAS_GRAVE = "mas_grave"  # el no ideal de menor umbral_minimo
NOTIFICA_NO_IDEALES = "no_ideales"  # todos los no ideales


@dataclass(frozen=True)
class RolPrueba:
    nombre: str
    alcance: str
    cargo: str
    funcionarios: int
    permisos: tuple
    notifica: str | None = None
    recibe_todos: bool = False


ROL_INSPECTOR = "Inspector"
ROL_PROFESOR_JEFE = "Profesor jefe"
CARGO_PROFESOR = "Profesor"

# En este orden se asignan los RUT (99000001-0 a 99000027-0).
ROLES = (
    RolPrueba(
        "Asistente social", Rol.ALCANCE_TODOS, "Asistente social", 3,
        ("revisar_alertas", "ver_monitoreo", "gestionar_justificaciones"),
        recibe_todos=True,
    ),
    RolPrueba(
        "Rector", Rol.ALCANCE_TODOS, "Rector", 3,
        ("revisar_alertas", "ver_monitoreo", "configurar_umbrales"),
        NOTIFICA_MAS_GRAVE,
    ),
    RolPrueba(
        "Inspector general", Rol.ALCANCE_TODOS, "Inspector general", 3,
        ("revisar_alertas", "ver_monitoreo", "gestionar_justificaciones", "cargar_datos"),
        NOTIFICA_MAS_GRAVE,
    ),
    RolPrueba(
        ROL_INSPECTOR, Rol.ALCANCE_SELECCIONADOS, "Inspector", len(GRUPOS),
        ("revisar_alertas", "ver_monitoreo", "gestionar_justificaciones"),
        NOTIFICA_NO_IDEALES,
    ),
    # Profesor jefe y Profesor comparten el cargo "Profesor": el formulario de
    # curso solo ofrece como profesor jefe a funcionarios con ese cargo.
    RolPrueba(
        ROL_PROFESOR_JEFE, Rol.ALCANCE_SELECCIONADOS, CARGO_PROFESOR, len(NIVELES) * len(GRUPOS),
        ("revisar_alertas", "ver_monitoreo"),
        NOTIFICA_NO_IDEALES,
    ),
    RolPrueba(
        "Profesor", Rol.ALCANCE_SELECCIONADOS, CARGO_PROFESOR, 3,
        ("ver_monitoreo",),
    ),
)

# Inspectores de contraste (cargo y rol Inspector), con los RUT siguientes.
# usuario del correo tras el "+", nombre, funcionario activo, cuenta activa
CONTRASTE = (
    ("inspectorinactivo", "Inspector Prueba inactivo", False, True),
    ("inspectorcuentainactiva", "Inspector Prueba cuenta inactiva", True, False),
)

CLAVES_CREADOS = (
    "roles", "permisos", "permisos_rol", "cargos", "funcionarios", "cuentas",
    "periodos", "cursos", "profesores_jefe", "funcionario_cursos", "estados_rol",
)

AVISO_SIN_ESTADOS = (
    "No hay estados de alerta no ideales: los roles nuevos quedaron sin estados que los notifiquen."
)


class AmbientePruebaError(Exception):
    """El ambiente no se puede preparar sin modificar datos existentes."""


def _slug(nombre):
    sin_tildes = unicodedata.normalize("NFD", nombre.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn"))


def _correo(usuario_extra):
    usuario, dominio = CORREO_BASE.split("@")
    return f"{usuario}+{usuario_extra}@{dominio}"


def correo_de_prueba(rol_nombre, numero):
    return _correo(f"{_slug(rol_nombre)}{numero}")


def aviso_sin_estados(creados):
    """Aviso para el mensaje si se crearon roles y no hay estados no ideales; "" si no."""
    if creados["roles"] and not Estado.objects.filter(es_no_ideal=True).exists():
        return AVISO_SIN_ESTADOS
    return ""


def _cargo(nombre, creados):
    cargo, creado = Cargo.objects.get_or_create(nombre__iexact=nombre, defaults={"nombre": nombre})
    creados["cargos"] += creado
    return cargo


def _funcionario(correo, nombre, consecutivo, cargo, rol, creados, activo=True, cuenta_activa=True):
    """El funcionario con ese correo; si no existe, lo crea con su cuenta."""
    existente = Funcionario.objects.filter(email__iexact=correo).first()
    if existente is not None:
        return existente  # no se toca (ni se le crea cuenta)
    rut = f"{RUT_BASE + consecutivo}-{RUT_DV}"
    if Funcionario.objects.filter(rut=rut).exists():
        raise AmbientePruebaError(
            f"El RUT de prueba {rut} ya lo usa otro funcionario (no es {correo}). "
            "No se creó nada; revisa ese funcionario antes de reintentar."
        )
    funcionario = Funcionario.objects.create(
        cargo=cargo, rut=rut, nombre=nombre, email=correo, activo=activo,
    )
    Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=cuenta_activa)
    creados["funcionarios"] += 1
    creados["cuentas"] += 1
    return funcionario


@transaction.atomic
def preparar_ambiente_prueba():
    """Crea lo que falte y devuelve cuántos registros creó de cada tipo."""
    creados = dict.fromkeys(CLAVES_CREADOS, 0)

    # 1. Permisos.
    permisos = {}
    for codigo, (nombre, descripcion) in PERMISOS.items():
        permisos[codigo], creado = Permiso.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "descripcion": descripcion},
        )
        creados["permisos"] += creado

    # 2. Período del año actual.
    anio = timezone.localdate().year
    periodo, creado = PeriodoAcademico.objects.get_or_create(
        anio=anio,
        defaults={
            "fecha_inicio": datetime.date(anio, 3, 1),
            "fecha_fin": datetime.date(anio, 12, 31),
        },
    )
    creados["periodos"] += creado

    # 3. Cursos en orden (nivel, grupo): posición 1 = 1°A ... 12 = 4°C.
    cursos_nuevos = []  # (posición, grupo, curso) de los creados en esta pulsación
    combinaciones = [(nivel, grupo) for nivel in NIVELES for grupo in GRUPOS]
    for posicion, (nivel, grupo) in enumerate(combinaciones, start=1):
        curso, creado = Curso.objects.get_or_create(
            periodo=periodo, nivel=nivel, grupo__iexact=grupo, defaults={"grupo": grupo},
        )
        if creado:
            cursos_nuevos.append((posicion, grupo, curso))
            creados["cursos"] += 1

    # 4. Roles, cargos y funcionarios.
    no_ideales = list(Estado.objects.filter(es_no_ideal=True).order_by("umbral_minimo", "pk"))
    estados_que_notifican = {
        None: [],
        NOTIFICA_MAS_GRAVE: no_ideales[:1],
        NOTIFICA_NO_IDEALES: no_ideales,
    }
    roles, cargos, funcionarios = {}, {}, {}  # por nombre del rol
    consecutivo = 0
    for datos in ROLES:
        rol, rol_creado = Rol.objects.get_or_create(
            nombre__iexact=datos.nombre,
            defaults={
                "nombre": datos.nombre,
                "alcance": datos.alcance,
                "recibe_todos_los_cursos_marcados": datos.recibe_todos,
            },
        )
        if rol_creado:
            # A un rol que ya existía no se le agrega nada.
            creados["roles"] += 1
            for codigo in datos.permisos:
                RolPermiso.objects.create(rol=rol, permiso=permisos[codigo])
                creados["permisos_rol"] += 1
            for estado in estados_que_notifican[datos.notifica]:
                EstadoNotificaRol.objects.create(estado=estado, rol=rol)
                creados["estados_rol"] += 1
        roles[datos.nombre] = rol
        cargos[datos.nombre] = cargo = _cargo(datos.cargo, creados)
        funcionarios[datos.nombre] = []
        for numero in range(1, datos.funcionarios + 1):
            consecutivo += 1  # avanza aunque el funcionario ya exista
            funcionarios[datos.nombre].append(_funcionario(
                correo_de_prueba(datos.nombre, numero), f"{datos.nombre} Prueba {numero}",
                consecutivo, cargo, rol, creados,
            ))

    # 5. Inspectores de contraste.
    contraste = []
    for usuario_extra, nombre, activo, cuenta_activa in CONTRASTE:
        consecutivo += 1
        contraste.append(_funcionario(
            _correo(usuario_extra), nombre, consecutivo,
            cargos[ROL_INSPECTOR], roles[ROL_INSPECTOR], creados,
            activo=activo, cuenta_activa=cuenta_activa,
        ))

    # 6. Conexiones, solo con los cursos creados en esta pulsación.
    for posicion, grupo, curso in cursos_nuevos:
        jefe = funcionarios[ROL_PROFESOR_JEFE][posicion - 1]
        ya_es_jefe = Curso.objects.filter(periodo=periodo, profesor_jefe=jefe).exists()
        if curso.profesor_jefe_id is None and not ya_es_jefe:
            curso.profesor_jefe = jefe
            curso.save()  # corre full_clean
            creados["profesores_jefe"] += 1

        asignados = [funcionarios[ROL_INSPECTOR][GRUPOS.index(grupo)]]
        if (curso.nivel, grupo) == CURSO_CONTRASTE:
            asignados += contraste
        for funcionario in asignados:
            _, creado = FuncionarioCurso.objects.get_or_create(funcionario=funcionario, curso=curso)
            creados["funcionario_cursos"] += creado

    return creados
