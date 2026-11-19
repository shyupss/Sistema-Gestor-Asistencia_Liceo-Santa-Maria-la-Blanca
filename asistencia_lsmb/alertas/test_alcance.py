import datetime
import re
from pathlib import Path

from django.db.models import QuerySet
from django.test import TestCase

from academico.models import Curso, PeriodoAcademico
from alertas.models import Cargo, Cuenta, Funcionario, FuncionarioCurso, Permiso, Rol, RolPermiso
from alertas.queries import alcance_queries
from alertas.queries.alcance_queries import cursos_en_alcance, tiene_permiso

CODIGO = "ver_cursos_de_prueba"


def _periodo(anio):
    return PeriodoAcademico.objects.create(
        anio=anio, fecha_inicio=datetime.date(anio, 3, 1), fecha_fin=datetime.date(anio, 12, 31),
    )


def _cursos(periodo):
    """1°A, 1°B, 2°A y 2°B del período, por (nivel, grupo)."""
    return {
        (nivel, grupo): Curso.objects.create(periodo=periodo, nivel=nivel, grupo=grupo)
        for nivel in (1, 2) for grupo in ("A", "B")
    }


class AlcanceTests(TestCase):
    def setUp(self):
        self.periodo = _periodo(2026)
        self.otro_periodo = _periodo(2025)
        self.cursos = _cursos(self.periodo)
        self.otros_cursos = _cursos(self.otro_periodo)
        self.cargo = Cargo.objects.create(nombre="Cargo de los tests de alcance")
        self.permiso = Permiso.objects.create(codigo=CODIGO, nombre="Ver cursos de prueba")
        self.otro_permiso = Permiso.objects.create(codigo="otro_permiso_de_prueba", nombre="Otro")
        self.rol_todos = Rol.objects.create(nombre="Rol amplio de prueba", alcance=Rol.ALCANCE_TODOS)
        self.rol_seleccionados = Rol.objects.create(
            nombre="Rol acotado de prueba", alcance=Rol.ALCANCE_SELECCIONADOS,
        )
        for rol in (self.rol_todos, self.rol_seleccionados):
            RolPermiso.objects.create(rol=rol, permiso=self.permiso)
        self._consecutivo = 0

    def _funcionario(self, rol=None, activo=True, cuenta_activa=True):
        """Funcionario con cuenta en `rol`; sin cuenta si rol es None."""
        self._consecutivo += 1
        n = self._consecutivo
        funcionario = Funcionario.objects.create(
            cargo=self.cargo, rut=f"{n}0000000-{n}", nombre=f"Funcionario {n}",
            email=f"funcionario{n}@liceo.cl", activo=activo,
        )
        if rol is not None:
            Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=cuenta_activa)
        return funcionario

    def _asignar(self, funcionario, *cursos):
        for curso in cursos:
            FuncionarioCurso.objects.create(funcionario=funcionario, curso=curso)

    def _jefe(self, funcionario, curso):
        curso.profesor_jefe = funcionario
        curso.save()

    def _alcance(self, funcionario, periodo=None):
        return set(cursos_en_alcance(funcionario, periodo or self.periodo))

    # --- cursos_en_alcance ---------------------------------------------------

    def test_rol_todos_ve_todos_los_cursos_del_periodo(self):
        funcionario = self._funcionario(self.rol_todos)
        self.assertEqual(self._alcance(funcionario), set(self.cursos.values()))
        self.assertEqual(self._alcance(funcionario, self.otro_periodo), set(self.otros_cursos.values()))

    def test_rol_seleccionados_ve_solo_los_asignados(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self._asignar(funcionario, self.cursos[(1, "A")], self.cursos[(2, "B")])
        self.assertEqual(
            self._alcance(funcionario), {self.cursos[(1, "A")], self.cursos[(2, "B")]},
        )

    def test_rol_seleccionados_sin_asignaciones_no_ve_nada(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self.assertEqual(self._alcance(funcionario), set())

    def test_profesor_jefe_sin_asignacion_ve_su_curso(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self._jefe(funcionario, self.cursos[(1, "B")])
        self.assertEqual(self._alcance(funcionario), {self.cursos[(1, "B")]})

    def test_profesor_jefe_asignado_al_mismo_curso_aparece_una_vez(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        curso = self.cursos[(1, "A")]
        self._jefe(funcionario, curso)
        self._asignar(funcionario, curso)
        resultado = cursos_en_alcance(funcionario, self.periodo)
        self.assertEqual(list(resultado), [curso])
        self.assertEqual(resultado.count(), 1)

    def test_suma_asignados_y_jefatura_sin_duplicados(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self._jefe(funcionario, self.cursos[(1, "A")])
        self._asignar(funcionario, self.cursos[(1, "A")], self.cursos[(2, "A")])
        resultado = cursos_en_alcance(funcionario, self.periodo)
        self.assertEqual(resultado.count(), 2)
        self.assertEqual(set(resultado), {self.cursos[(1, "A")], self.cursos[(2, "A")]})

    def test_el_periodo_filtra_asignaciones_y_jefatura(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self._asignar(funcionario, self.cursos[(1, "A")], self.otros_cursos[(1, "B")])
        self._jefe(funcionario, self.otros_cursos[(2, "B")])
        self.assertEqual(self._alcance(funcionario), {self.cursos[(1, "A")]})
        self.assertEqual(
            self._alcance(funcionario, self.otro_periodo),
            {self.otros_cursos[(1, "B")], self.otros_cursos[(2, "B")]},
        )

    def test_acepta_el_id_del_periodo(self):
        funcionario = self._funcionario(self.rol_todos)
        self.assertEqual(
            set(cursos_en_alcance(funcionario, self.periodo.pk)), set(self.cursos.values()),
        )

    # --- Sin acceso: vacío y sin permisos --------------------------------------

    def _sin_acceso(self, funcionario):
        # Con todo lo que le daría cursos si tuviera acceso.
        self._asignar(funcionario, self.cursos[(1, "A")])
        self._jefe(funcionario, self.cursos[(2, "A")])
        resultado = cursos_en_alcance(funcionario, self.periodo)
        self.assertIsInstance(resultado, QuerySet)
        self.assertFalse(resultado.exists())
        self.assertFalse(tiene_permiso(funcionario, CODIGO))

    def test_cuenta_inactiva(self):
        for rol in (self.rol_todos, self.rol_seleccionados):
            with self.subTest(alcance=rol.alcance):
                self._sin_acceso(self._funcionario(rol, cuenta_activa=False))

    def test_funcionario_inactivo(self):
        for rol in (self.rol_todos, self.rol_seleccionados):
            with self.subTest(alcance=rol.alcance):
                self._sin_acceso(self._funcionario(rol, activo=False))

    def test_funcionario_sin_cuenta(self):
        funcionario = self._funcionario(rol=None)
        self.assertFalse(Cuenta.objects.filter(funcionario=funcionario).exists())
        self._sin_acceso(funcionario)

    # --- tiene_permiso ---------------------------------------------------------

    def test_permiso_presente_y_ausente(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        self.assertTrue(tiene_permiso(funcionario, CODIGO))
        # Existe, pero el rol no lo tiene.
        self.assertFalse(tiene_permiso(funcionario, self.otro_permiso.codigo))
        # No existe.
        self.assertFalse(tiene_permiso(funcionario, "codigo_inexistente"))

    def test_el_permiso_de_otro_rol_no_cuenta(self):
        RolPermiso.objects.create(rol=self.rol_todos, permiso=self.otro_permiso)
        funcionario = self._funcionario(self.rol_seleccionados)
        self.assertFalse(tiene_permiso(funcionario, self.otro_permiso.codigo))
        self.assertTrue(tiene_permiso(self._funcionario(self.rol_todos), self.otro_permiso.codigo))

    def test_tiene_permiso_es_una_sola_consulta(self):
        funcionario = self._funcionario(self.rol_seleccionados)
        with self.assertNumQueries(1):
            tiene_permiso(funcionario, CODIGO)

    # --- No depende de nombres -------------------------------------------------

    def test_un_rol_con_cualquier_nombre_funciona_igual(self):
        rol = Rol.objects.create(
            nombre="Coordinación de convivencia escolar", alcance=Rol.ALCANCE_TODOS,
        )
        RolPermiso.objects.create(rol=rol, permiso=self.permiso)
        funcionario = self._funcionario(rol)
        self.assertEqual(self._alcance(funcionario), set(self.cursos.values()))
        self.assertTrue(tiene_permiso(funcionario, CODIGO))

    def test_el_nombre_del_rol_no_da_alcance(self):
        # Un rol llamado "Rector" con alcance seleccionados solo ve lo asignado.
        rol = Rol.objects.create(nombre="Rector", alcance=Rol.ALCANCE_SELECCIONADOS)
        funcionario = self._funcionario(rol)
        self._asignar(funcionario, self.cursos[(2, "B")])
        self.assertEqual(self._alcance(funcionario), {self.cursos[(2, "B")]})
        self.assertFalse(tiene_permiso(funcionario, CODIGO))

    # --- Queryset --------------------------------------------------------------

    def test_retorna_un_queryset_filtrable(self):
        seleccionados = self._funcionario(self.rol_seleccionados)
        self._asignar(seleccionados, self.cursos[(1, "A")], self.cursos[(2, "A")])
        self._jefe(seleccionados, self.cursos[(1, "B")])
        casos = (
            (self._funcionario(self.rol_todos), {self.cursos[(1, "A")], self.cursos[(1, "B")]}),
            (seleccionados, {self.cursos[(1, "A")], self.cursos[(1, "B")]}),
        )
        for funcionario, nivel_1 in casos:
            with self.subTest(funcionario=funcionario.nombre):
                resultado = cursos_en_alcance(funcionario, self.periodo)
                self.assertIsInstance(resultado, QuerySet)
                self.assertEqual(resultado.model, Curso)
                self.assertEqual(set(resultado.filter(nivel=1)), nivel_1)
                self.assertEqual(
                    list(resultado.filter(grupo="A").order_by("nivel").values_list("nivel", flat=True)),
                    [1, 2],
                )


class AlcanceIndependenciaTests(TestCase):
    """El módulo no importa de monitoreo ni de asistencia, ni nombra roles o estados."""

    def _codigo(self):
        return Path(alcance_queries.__file__).read_text(encoding="utf-8")

    def test_no_importa_de_monitoreo_ni_asistencia(self):
        codigo = self._codigo()
        for app in ("monitoreo", "asistencia"):
            with self.subTest(app=app):
                self.assertIsNone(re.search(rf"^\s*(from|import)\s+{app}\b", codigo, re.MULTILINE))

    def test_no_nombra_roles_ni_estados(self):
        codigo = self._codigo().lower()
        for nombre in (
            "asistente social", "rector", "inspector", "profesor jefe",
            "óptimo", "adecuado", "atención", "crítico", "revisar_alertas",
        ):
            with self.subTest(nombre=nombre):
                self.assertNotIn(nombre, codigo)
