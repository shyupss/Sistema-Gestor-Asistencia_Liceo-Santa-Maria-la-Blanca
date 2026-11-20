"""Resumen de alertas por destinatario: construir_resumen y construir_resumenes.

Las fechas son relativas a hoy y los roles, estados y cursos tienen nombres
arbitrarios: solo importan Rol.alcance, recibe_todos_los_cursos_marcados, el
permiso, EstadoNotificaRol y es_no_ideal.
"""
import dataclasses
import datetime
import importlib
import itertools
import re
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import (
    Alerta, Cargo, Cuenta, Estado, EstadoAlumno, EstadoNotificaRol, Funcionario,
    FuncionarioCurso, Permiso, Rol, RolPermiso,
)
from alertas.queries.alerta_queries import alertas_por_curso, alertas_vigentes

UN_DIA = datetime.timedelta(days=1)


def _resumen():
    return importlib.import_module("alertas.services.resumen_alertas")


class ResumenBase(TestCase):
    """Datos comunes. Sin métodos de test: test_comando_resumen la reutiliza."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.periodo = self._periodo(self.hoy.year)
        self.otro_periodo = self._periodo(self.hoy.year - 1)
        # Creados fuera de orden, para probar el orden por (nivel, grupo).
        self.c2a = self._curso(2, "A")
        self.c1b = self._curso(1, "B")
        self.c1a = self._curso(1, "A")
        self.curso_otro_periodo = self._curso(1, "A", self.otro_periodo)
        self.leve = Estado.objects.create(nombre="Leve", umbral_minimo=70, es_no_ideal=True)
        self.grave = Estado.objects.create(nombre="Grave", umbral_minimo=0, es_no_ideal=True)
        self.bien = Estado.objects.create(nombre="Bien", umbral_minimo=90, es_no_ideal=False)
        self.permiso = Permiso.objects.get_or_create(
            codigo="revisar_alertas", defaults={"nombre": "Revisar alertas"},
        )[0]
        self.cargo = Cargo.objects.create(nombre="Cargo de prueba")
        self._numeros = itertools.count(1)

    # --- datos ---

    def _periodo(self, anio):
        return PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=self.hoy - 60 * UN_DIA, fecha_fin=self.hoy + 60 * UN_DIA,
        )

    def _curso(self, nivel, grupo, periodo=None):
        return Curso.objects.create(periodo=periodo or self.periodo, nivel=nivel, grupo=grupo)

    def _rol(self, nombre, alcance=Rol.ALCANCE_SELECCIONADOS, recibe_todos=False, estados=(),
             con_permiso=True):
        rol = Rol.objects.create(
            nombre=nombre, alcance=alcance, recibe_todos_los_cursos_marcados=recibe_todos,
        )
        if con_permiso:
            RolPermiso.objects.create(rol=rol, permiso=self.permiso)
        for estado in estados:
            EstadoNotificaRol.objects.create(rol=rol, estado=estado)
        return rol

    def _funcionario(self, rol=None, nombre=None, cursos=(), activo=True, cuenta_activa=True):
        numero = next(self._numeros)
        funcionario = Funcionario.objects.create(
            cargo=self.cargo, rut=f"{numero:08d}-9", nombre=nombre or f"Funcionario {numero}",
            email=f"funcionario{numero}@liceo.cl", activo=activo,
        )
        if rol is not None:
            Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=cuenta_activa)
        for curso in cursos:
            FuncionarioCurso.objects.create(funcionario=funcionario, curso=curso)
        return funcionario

    def _alumno(self, nombre="Alumno"):
        return Alumno.objects.create(nombre=nombre, rut=f"{next(self._numeros):08d}-1")

    def _matricula(self, alumno, curso, fecha_termino=None):
        return Matricula.objects.create(
            alumno=alumno, curso=curso, periodo=curso.periodo,
            estado_matricula=EstadoMatricula.objects.get_or_create(nombre="vigente")[0],
            fecha_matricula=self.hoy - 30 * UN_DIA, fecha_termino=fecha_termino,
        )

    def _caso(self, curso, estado=None, porcentaje=60, nombre="Alumno", fecha_termino=None,
              **campos):
        """Alumno matriculado en `curso`, su EstadoAlumno (si hay porcentaje) y una alerta."""
        estado = estado or self.leve
        alumno = self._alumno(nombre)
        self._matricula(alumno, curso, fecha_termino)
        if porcentaje is not None:
            EstadoAlumno.objects.create(
                alumno=alumno, periodo=curso.periodo, estado=estado,
                porcentaje_asistencia=porcentaje,
            )
        return Alerta.objects.create(alumno=alumno, periodo=curso.periodo, estado=estado, **campos)

    # --- utilidades ---

    def _construir(self, funcionario, **kwargs):
        return _resumen().construir_resumen(funcionario, **kwargs)

    @staticmethod
    def _vista(resumen):
        """[(curso, [alerta_id, ...]), ...] de un resumen, para comparar."""
        return [(c.curso, [a.alerta_id for a in c.alumnos]) for c in resumen.cursos]


class ResumenPorRolTests(ResumenBase):
    def setUp(self):
        super().setUp()
        self.c1a_leve = self._caso(self.c1a, self.leve)
        self.c1a_grave = self._caso(self.c1a, self.grave)
        self.c1b_leve = self._caso(self.c1b, self.leve)
        self.c2a_grave = self._caso(self.c2a, self.grave)

    def test_recibe_todos_ve_todos_los_cursos_y_gravedades_sin_cursos_asignados(self):
        rol = self._rol("Rol general", recibe_todos=True)
        resumen = self._construir(self._funcionario(rol))
        self.assertEqual(self._vista(resumen), [
            (self.c1a, [self.c1a_grave.pk, self.c1a_leve.pk]),
            (self.c1b, [self.c1b_leve.pk]),
            (self.c2a, [self.c2a_grave.pk]),
        ])
        self.assertEqual((resumen.total_cursos, resumen.total_alumnos), (3, 4))

    def test_alcance_total_con_tabla_de_estados_ve_solo_esos_estados(self):
        rol = self._rol("Rol total", Rol.ALCANCE_TODOS, estados=[self.grave])
        resumen = self._construir(self._funcionario(rol))
        self.assertEqual(self._vista(resumen), [
            (self.c1a, [self.c1a_grave.pk]),
            (self.c2a, [self.c2a_grave.pk]),
        ])
        self.assertEqual([c.total_alumnos for c in resumen.cursos], [1, 1])
        self.assertEqual((resumen.total_cursos, resumen.total_alumnos), (2, 2))

    def test_alcance_asignado_ve_solo_sus_cursos_por_asignacion_y_jefatura(self):
        rol = self._rol("Rol asignado", estados=[self.leve, self.grave])
        funcionario = self._funcionario(rol, cursos=[self.c1a])
        self.c2a.profesor_jefe = funcionario
        self.c2a.save()
        self.assertEqual(self._vista(self._construir(funcionario)), [
            (self.c1a, [self.c1a_grave.pk, self.c1a_leve.pk]),
            (self.c2a, [self.c2a_grave.pk]),
        ])

    def test_sin_tabla_de_estados_y_sin_el_flag_no_recibe_nada(self):
        for alcance in (Rol.ALCANCE_TODOS, Rol.ALCANCE_SELECCIONADOS):
            with self.subTest(alcance=alcance):
                rol = self._rol(f"Rol sin estados {alcance}", alcance)
                self.assertIsNone(self._construir(self._funcionario(rol, cursos=[self.c1a])))

    def test_jefatura_solo_con_datos_ve_su_curso_y_todos_los_no_ideales(self):
        rol = self._rol("Rol jefatura", estados=Estado.objects.filter(es_no_ideal=True))
        funcionario = self._funcionario(rol)
        self.c1a.profesor_jefe = funcionario
        self.c1a.save()
        self.assertEqual(self._vista(self._construir(funcionario)), [
            (self.c1a, [self.c1a_grave.pk, self.c1a_leve.pk]),
        ])

    def test_sin_el_permiso_no_es_destinatario(self):
        rol = self._rol("Rol general sin permiso", recibe_todos=True, con_permiso=False)
        self.assertIsNone(self._construir(self._funcionario(rol)))
        rol_con_permiso = self._rol("Rol general", recibe_todos=True)
        for caso, funcionario in (
            ("inactivo", self._funcionario(rol_con_permiso, activo=False)),
            ("cuenta inactiva", self._funcionario(rol_con_permiso, cuenta_activa=False)),
            ("sin cuenta", self._funcionario()),
        ):
            with self.subTest(caso=caso):
                self.assertIsNone(self._construir(funcionario))


class ResumenFiltrosTests(ResumenBase):
    def setUp(self):
        super().setUp()
        self.general = self._funcionario(self._rol("Rol general", recibe_todos=True))

    def test_revisadas_no_aparecen_ni_marcan_el_curso(self):
        sin_revisar = self._caso(self.c1a)
        self._caso(self.c1a, revisada=True)
        self._caso(self.c1b, revisada=True)
        resumen = self._construir(self.general)
        self.assertEqual(self._vista(resumen), [(self.c1a, [sin_revisar.pk])])
        self.assertEqual(resumen.cursos[0].total_alumnos, 1)

    def test_cerradas_de_otro_periodo_o_sin_matricula_activa_no_aparecen(self):
        self._caso(self.c1a, fecha_cierre=timezone.now(), motivo_cierre="recuperado")
        self._caso(self.curso_otro_periodo)
        self._caso(self.c1b, fecha_termino=self.hoy)
        valida = self._caso(self.c2a)
        self.assertEqual(self._vista(self._construir(self.general)), [(self.c2a, [valida.pk])])

    def test_solo_alertas_que_no_se_ven_da_none(self):
        self._caso(self.c1a, revisada=True)
        self.assertIsNone(self._construir(self.general))

    def test_sin_periodo_del_anio_de_hoy(self):
        self._caso(self.c1a)
        sin_periodo = datetime.date(1990, 6, 1)
        self.assertIsNone(self._construir(self.general, hoy=sin_periodo))
        self.assertEqual(_resumen().construir_resumenes(hoy=sin_periodo), [])

    def test_acepta_el_periodo_explicito(self):
        alerta = self._caso(self.c1a)
        resumen = self._construir(self.general, periodo=self.periodo)
        self.assertEqual(resumen.periodo, self.periodo)
        self.assertEqual(self._vista(resumen), [(self.c1a, [alerta.pk])])

    def test_alertas_vigentes_toma_estados_vacios_como_ningun_estado(self):
        self._caso(self.c1a)
        self.assertEqual(list(alertas_vigentes(self.periodo, estados=[])), [])
        self.assertEqual(list(alertas_vigentes(self.periodo, estados=Estado.objects.none())), [])
        self.assertEqual(len(alertas_vigentes(self.periodo, estados=None)), 1)


class ResumenContenidoTests(ResumenBase):
    def setUp(self):
        super().setUp()
        self.general = self._funcionario(self._rol("Rol general", recibe_todos=True))

    def test_lista_los_primeros_cinco_y_cuenta_los_restantes(self):
        self.assertEqual(_resumen().ALUMNOS_POR_CURSO, 5)
        for curso, cantidad in ((self.c1a, 5), (self.c1b, 6), (self.c2a, 12)):
            for indice in range(cantidad):
                self._caso(curso, porcentaje=40 + indice, nombre=f"Alumno {indice:02d}")
        resumen = self._construir(self.general)
        self.assertEqual(
            [(c.curso, c.total_alumnos, len(c.alumnos), c.restantes) for c in resumen.cursos],
            [(self.c1a, 5, 5, 0), (self.c1b, 6, 5, 1), (self.c2a, 12, 5, 7)],
        )
        self.assertEqual((resumen.total_cursos, resumen.total_alumnos), (3, 23))
        # Los listados son los primeros en el orden de alertas_por_curso.
        self.assertEqual(
            [a.nombre for a in resumen.cursos[2].alumnos],
            [f"Alumno {indice:02d}" for indice in range(5)],
        )

    def test_orden_de_cursos_y_alumnos_igual_que_alertas_por_curso(self):
        self._caso(self.c2a, self.leve, 50, "Ana")
        self._caso(self.c1a, self.leve, 50, "Carla")
        self._caso(self.c1a, self.grave, 60, "Diego")
        self._caso(self.c1a, self.grave, 40, "Elena")
        self._caso(self.c1a, self.leve, 50, "Beto")
        self._caso(self.c1b, self.leve, 10, "Fabian")
        resumen = self._construir(self.general)
        esperado = [
            (curso, [alerta.pk for alerta in alertas])
            for curso, alertas in alertas_por_curso(self.periodo, solo_sin_revisar=True)
        ]
        self.assertEqual(self._vista(resumen), esperado)
        self.assertEqual([c.curso for c in resumen.cursos], [self.c1a, self.c1b, self.c2a])
        self.assertEqual(
            [a.nombre for a in resumen.cursos[0].alumnos], ["Elena", "Diego", "Beto", "Carla"],
        )

    def test_campos_de_cada_alumno_y_curso(self):
        alerta = self._caso(self.c1a, self.grave, Decimal("62.50"), "Ana Pérez")
        [curso] = self._construir(self.general).cursos
        self.assertEqual(curso.nombre, "I°A")
        [alumno] = curso.alumnos
        self.assertEqual(alumno.alerta_id, alerta.pk)
        self.assertEqual(alumno.nombre, "Ana Pérez")
        self.assertEqual(alumno.estado, "Grave")
        self.assertEqual(alumno.porcentaje, 62.5)
        self.assertIsInstance(alumno.porcentaje, float)

    def test_nivel_segun_el_orden_de_umbral(self):
        self._caso(self.c1a, self.leve, nombre="Leve")
        self._caso(self.c1a, self.grave, nombre="Grave")
        niveles = {a.nombre: a.nivel for a in self._construir(self.general).cursos[0].alumnos}
        self.assertEqual(niveles, {"Leve": "atencion", "Grave": "critico"})

    def test_porcentaje_none_sin_estado_alumno(self):
        self._caso(self.c1a, porcentaje=None)
        self.assertIsNone(self._construir(self.general).cursos[0].alumnos[0].porcentaje)

    def test_fecha_alerta_es_el_dia_local(self):
        alerta = self._caso(self.c1a)
        # 02:00 UTC es el día anterior en Chile (UTC-3 o UTC-4).
        utc = datetime.datetime(self.hoy.year, 3, 10, 2, 0, tzinfo=datetime.timezone.utc)
        Alerta.objects.filter(pk=alerta.pk).update(fecha_creacion=utc)
        fecha = self._construir(self.general).cursos[0].alumnos[0].fecha_alerta
        self.assertEqual(fecha, datetime.date(self.hoy.year, 3, 9))

    def test_las_dataclasses_son_inmutables(self):
        self._caso(self.c1a)
        resumen = self._construir(self.general)
        curso = resumen.cursos[0]
        for objeto, campo in ((resumen, "total_alumnos"), (curso, "restantes"), (curso.alumnos[0], "nombre")):
            with self.subTest(clase=type(objeto).__name__), self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(objeto, campo, None)
        self.assertIsInstance(resumen.cursos, tuple)
        self.assertIsInstance(curso.alumnos, tuple)


class ConstruirResumenesTests(ResumenBase):
    def setUp(self):
        super().setUp()
        self.general = self._funcionario(self._rol("Rol general", recibe_todos=True))
        self.sin_estados = self._funcionario(self._rol("Rol sin estados", Rol.ALCANCE_TODOS))
        self.asignado = self._funcionario(
            self._rol("Rol asignado", estados=[self.leve, self.grave]), cursos=[self.c1a],
        )
        self.total_grave = self._funcionario(
            self._rol("Rol total grave", Rol.ALCANCE_TODOS, estados=[self.grave]),
        )
        self.sin_permiso = self._funcionario(
            self._rol("Rol general sin permiso", recibe_todos=True, con_permiso=False),
        )
        self._caso(self.c1a, self.leve)
        self._caso(self.c1a, self.grave)

    def test_un_resumen_por_destinatario_con_contenido_ordenado_por_id(self):
        resumenes = _resumen().construir_resumenes()
        self.assertEqual(
            [r.funcionario for r in resumenes], [self.general, self.asignado, self.total_grave],
        )
        self.assertEqual(len({r.funcionario.pk for r in resumenes}), len(resumenes))

    def test_respeta_el_parametro_funcionarios(self):
        construir = _resumen().construir_resumenes
        self.assertEqual(
            [r.funcionario for r in construir([self.total_grave, self.general])],
            [self.general, self.total_grave],
        )
        self.assertEqual(construir([self.sin_estados]), [])
        self.assertEqual(
            [r.funcionario for r in construir(Funcionario.objects.filter(pk=self.asignado.pk))],
            [self.asignado],
        )
        # Quien no es destinatario no recibe nada aunque se lo pase explícitamente.
        self.assertEqual(construir([self.sin_permiso]), [])

    def test_resuelve_el_periodo_una_sola_vez(self):
        modulo = _resumen()
        with mock.patch.object(modulo, "periodo_actual", wraps=modulo.periodo_actual) as periodo:
            modulo.construir_resumenes()
        self.assertEqual(periodo.call_count, 1)

    def _consultas(self, funcion):
        with CaptureQueriesContext(connection) as contexto:
            funcion()
        return [consulta["sql"] for consulta in contexto.captured_queries]

    def test_consultas_constantes_por_destinatario_y_solo_lectura(self):
        construir = _resumen().construir_resumenes
        uno = lambda: _resumen().construir_resumen(self.general)  # noqa: E731
        pocas_todos, pocas_uno = self._consultas(construir), self._consultas(uno)
        for indice in range(28):
            self._caso(
                (self.c1a, self.c1b, self.c2a)[indice % 3], (self.leve, self.grave)[indice % 2],
            )
        muchas_todos, muchas_uno = self._consultas(construir), self._consultas(uno)
        self.assertEqual(Alerta.objects.count(), 30)
        self.assertEqual(len(muchas_todos), len(pocas_todos))
        self.assertEqual(len(muchas_uno), len(pocas_uno))
        for sql in pocas_todos + muchas_todos:
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"), sql)


class IndependenciaTests(TestCase):
    """Los módulos nuevos no importan de monitoreo ni de asistencia, ni nombran roles o estados."""

    MODULOS = (
        "queries/destinatario_queries.py",
        "services/resumen_alertas.py",
        "management/commands/resumen_alertas.py",
    )

    def _codigos(self):
        base = Path(importlib.import_module("alertas").__file__).resolve().parent
        return {modulo: (base / modulo).read_text(encoding="utf-8") for modulo in self.MODULOS}

    def test_no_importan_de_monitoreo_ni_asistencia(self):
        for modulo, codigo in self._codigos().items():
            for app in ("monitoreo", "asistencia"):
                with self.subTest(modulo=modulo, app=app):
                    self.assertIsNone(
                        re.search(rf"^\s*(from|import)\s+{app}\b", codigo, re.MULTILINE)
                    )

    def test_no_nombran_roles_ni_estados(self):
        for modulo, codigo in self._codigos().items():
            for nombre in (
                "asistente social", "rector", "inspector", "profesor jefe",
                "óptimo", "adecuado", "atención", "crítico",
            ):
                with self.subTest(modulo=modulo, nombre=nombre):
                    self.assertIsNone(re.search(rf"\b{re.escape(nombre)}\b", codigo.lower()))
