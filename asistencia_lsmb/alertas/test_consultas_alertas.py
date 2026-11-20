"""Consultas de alertas: periodo_actual, matriculas_activas, alertas_vigentes, cursos_marcados y alertas_por_curso.

Las fechas son relativas a hoy y los estados tienen nombres arbitrarios: solo
importan es_no_ideal y umbral_minimo.
"""
import datetime
import importlib
import itertools
import re
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.db import connection
from django.db.models import QuerySet
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import (
    Alerta, Cargo, Cuenta, Estado, EstadoAlumno, Funcionario, FuncionarioCurso, Rol,
)
from alertas.queries.alcance_queries import cursos_en_alcance
from alertas.services.alertas_service import sincronizar_alerta

UN_DIA = datetime.timedelta(days=1)


def _consulta(modulo, funcion):
    """Importa al llamar: antes de implementar, cada test falla por su cuenta."""
    def llamar(*args, **kwargs):
        return getattr(importlib.import_module(f"alertas.queries.{modulo}"), funcion)(*args, **kwargs)
    return llamar


periodo_actual = _consulta("periodo_queries", "periodo_actual")
matriculas_activas = _consulta("matricula_queries", "matriculas_activas")
alertas_vigentes = _consulta("alerta_queries", "alertas_vigentes")
cursos_marcados = _consulta("alerta_queries", "cursos_marcados")
alertas_por_curso = _consulta("alerta_queries", "alertas_por_curso")


class ConsultasBase(TestCase):
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
        self._ruts = itertools.count(1)

    def _periodo(self, anio):
        return PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=self.hoy - 60 * UN_DIA, fecha_fin=self.hoy + 60 * UN_DIA,
        )

    def _curso(self, nivel, grupo, periodo=None):
        return Curso.objects.create(periodo=periodo or self.periodo, nivel=nivel, grupo=grupo)

    def _alumno(self, nombre="Alumno"):
        return Alumno.objects.create(nombre=nombre, rut=f"{next(self._ruts):08d}-1")

    def _matricula(self, alumno, curso, fecha_matricula=None, fecha_termino=None):
        return Matricula.objects.create(
            alumno=alumno, curso=curso, periodo=curso.periodo,
            estado_matricula=EstadoMatricula.objects.get_or_create(nombre="vigente")[0],
            fecha_matricula=fecha_matricula or self.hoy - 30 * UN_DIA,
            fecha_termino=fecha_termino,
        )

    def _alerta(self, alumno, estado=None, periodo=None, **campos):
        return Alerta.objects.create(
            alumno=alumno, periodo=periodo or self.periodo, estado=estado or self.leve, **campos,
        )

    def _estado_alumno(self, alumno, porcentaje, estado=None, periodo=None):
        return EstadoAlumno.objects.create(
            alumno=alumno, periodo=periodo or self.periodo, estado=estado or self.leve,
            porcentaje_asistencia=porcentaje,
        )

    def _caso(self, curso, estado=None, porcentaje=60, nombre="Alumno", **campos):
        """Alumno con matrícula activa en `curso`, su EstadoAlumno (si hay porcentaje) y una alerta vigente."""
        estado = estado or self.leve
        alumno = self._alumno(nombre)
        self._matricula(alumno, curso)
        if porcentaje is not None:
            self._estado_alumno(alumno, porcentaje, estado, curso.periodo)
        return self._alerta(alumno, estado, curso.periodo, **campos)

    @staticmethod
    def _pks(objetos):
        return [objeto.pk for objeto in objetos]


class PeriodoActualTests(ConsultasBase):
    def test_devuelve_el_periodo_del_anio_de_hoy(self):
        self.assertEqual(periodo_actual(), self.periodo)

    def test_none_si_no_existe(self):
        self.assertIsNone(periodo_actual(datetime.date(1990, 6, 1)))

    def test_respeta_hoy(self):
        self.assertEqual(periodo_actual(datetime.date(self.hoy.year - 1, 6, 1)), self.otro_periodo)
        self.assertEqual(periodo_actual(self.hoy), self.periodo)


class MatriculasActivasTests(ConsultasBase):
    def setUp(self):
        super().setUp()
        self.nula = self._matricula(self._alumno(), self.c1a)
        self.termina_manana = self._matricula(self._alumno(), self.c1a, fecha_termino=self.hoy + UN_DIA)
        self.termina_hoy = self._matricula(self._alumno(), self.c1a, fecha_termino=self.hoy)
        self.termino_ayer = self._matricula(self._alumno(), self.c1a, fecha_termino=self.hoy - UN_DIA)
        # No se mira fecha_matricula: una que empieza en el futuro también es activa.
        self.futura = self._matricula(self._alumno(), self.c1a, fecha_matricula=self.hoy + 10 * UN_DIA)

    def test_nula_y_que_termina_manana_son_activas_hoy_y_ayer_no(self):
        esperadas = {self.nula, self.termina_manana, self.futura}
        self.assertEqual(set(matriculas_activas()), esperadas)
        self.assertEqual(set(matriculas_activas(self.hoy)), esperadas)

    def test_respeta_hoy(self):
        self.assertEqual(
            set(matriculas_activas(self.hoy - 2 * UN_DIA)),
            {self.nula, self.termina_manana, self.termina_hoy, self.termino_ayer, self.futura},
        )

    def test_devuelve_un_queryset_de_matriculas(self):
        resultado = matriculas_activas()
        self.assertIsInstance(resultado, QuerySet)
        self.assertEqual(resultado.model, Matricula)


class AlertasVigentesTests(ConsultasBase):
    def test_excluye_cerradas_y_de_otro_periodo(self):
        alumno = self._alumno()
        self._matricula(alumno, self.c1a)
        self._matricula(alumno, self.curso_otro_periodo)
        vigente = self._alerta(alumno)
        self._alerta(alumno, fecha_cierre=timezone.now(), motivo_cierre="recuperado")
        self._alerta(alumno, periodo=self.otro_periodo)
        self.assertEqual(self._pks(alertas_vigentes(self.periodo)), [vigente.pk])

    def test_solo_alumnos_con_matricula_activa_en_ese_periodo(self):
        sin_matricula = self._alumno()
        termina_hoy = self._alumno()
        self._matricula(termina_hoy, self.c1a, fecha_termino=self.hoy)
        solo_en_otro = self._alumno()
        self._matricula(solo_en_otro, self.curso_otro_periodo)
        termina_manana = self._alumno()
        self._matricula(termina_manana, self.c1a, fecha_termino=self.hoy + UN_DIA)
        for alumno in (sin_matricula, termina_hoy, solo_en_otro):
            self._alerta(alumno)
        incluida = self._alerta(termina_manana)

        self.assertEqual(self._pks(alertas_vigentes(self.periodo)), [incluida.pk])
        # Con hoy = mañana, la que termina mañana tampoco cuenta.
        self.assertEqual(list(alertas_vigentes(self.periodo, hoy=self.hoy + UN_DIA)), [])

    def test_acepta_el_periodo_como_id(self):
        alerta = self._caso(self.c1a)
        self.assertEqual(self._pks(alertas_vigentes(self.periodo.pk)), [alerta.pk])

    def test_curso_id_sale_de_la_matricula_activa(self):
        cambio = self._alumno()
        self._matricula(cambio, self.c1a, fecha_matricula=self.hoy - 50 * UN_DIA,
                        fecha_termino=self.hoy - 3 * UN_DIA)
        self._matricula(cambio, self.c1b, fecha_matricula=self.hoy - 3 * UN_DIA)

        activa_antigua = self._alumno()
        self._matricula(activa_antigua, self.c1a, fecha_matricula=self.hoy - 50 * UN_DIA)
        # Una terminada más reciente no le gana a la activa.
        self._matricula(activa_antigua, self.c2a, fecha_matricula=self.hoy - 10 * UN_DIA,
                        fecha_termino=self.hoy - 5 * UN_DIA)

        dos_activas = self._alumno()
        self._matricula(dos_activas, self.c1a, fecha_matricula=self.hoy - 50 * UN_DIA,
                        fecha_termino=self.hoy + 30 * UN_DIA)
        self._matricula(dos_activas, self.c2a, fecha_matricula=self.hoy - 10 * UN_DIA)

        empate = self._alumno()
        fecha = self.hoy - 20 * UN_DIA
        self._matricula(empate, self.c1a, fecha_matricula=fecha, fecha_termino=self.hoy + 30 * UN_DIA)
        self._matricula(empate, self.c1b, fecha_matricula=fecha)  # mismo día, mayor id

        esperado = {cambio: self.c1b, activa_antigua: self.c1a, dos_activas: self.c2a, empate: self.c1b}
        alertas = {self._alerta(alumno).pk: curso for alumno, curso in esperado.items()}
        self.assertEqual(
            {alerta.pk: alerta.curso_id for alerta in alertas_vigentes(self.periodo)},
            {pk: curso.pk for pk, curso in alertas.items()},
        )

    def test_porcentaje_sale_del_estado_alumno_del_mismo_periodo(self):
        alumno = self._alumno()
        self._matricula(alumno, self.c1a)
        self._estado_alumno(alumno, Decimal("72.50"))
        self._estado_alumno(alumno, Decimal("10.00"), periodo=self.otro_periodo)
        self._alerta(alumno)
        solo_en_otro = self._alumno()
        self._matricula(solo_en_otro, self.c1b)
        self._estado_alumno(solo_en_otro, Decimal("33.00"), periodo=self.otro_periodo)
        self._alerta(solo_en_otro)

        porcentajes = {a.alumno_id: a.porcentaje_asistencia for a in alertas_vigentes(self.periodo)}
        self.assertEqual(porcentajes, {alumno.pk: Decimal("72.50"), solo_en_otro.pk: None})

    def test_filtros_solos_y_combinados(self):
        a1 = self._caso(self.c1a, self.leve)
        a2 = self._caso(self.c1a, self.grave, revisada=True)
        a3 = self._caso(self.c1b, self.leve, revisada=True)
        a4 = self._caso(self.c2a, self.grave)

        def pks(**filtros):
            return set(self._pks(alertas_vigentes(self.periodo, **filtros)))

        # Por defecto las revisadas se incluyen.
        self.assertEqual(pks(), {a1.pk, a2.pk, a3.pk, a4.pk})
        # cursos: QuerySet, ids, instancias o vacío.
        self.assertEqual(pks(cursos=Curso.objects.filter(pk__in=[self.c1a.pk, self.c1b.pk])),
                         {a1.pk, a2.pk, a3.pk})
        self.assertEqual(pks(cursos=[self.c2a.pk]), {a4.pk})
        self.assertEqual(pks(cursos=[self.c1a]), {a1.pk, a2.pk})
        self.assertEqual(pks(cursos=[]), set())
        self.assertEqual(pks(cursos=Curso.objects.none()), set())
        # estados (sobre el estado de la alerta): QuerySet o ids.
        self.assertEqual(pks(estados=Estado.objects.filter(pk=self.grave.pk)), {a2.pk, a4.pk})
        self.assertEqual(pks(estados=[self.leve.pk]), {a1.pk, a3.pk})
        # solo_sin_revisar.
        self.assertEqual(pks(solo_sin_revisar=True), {a1.pk, a4.pk})
        # Combinados.
        self.assertEqual(pks(cursos=[self.c1a.pk, self.c1b.pk], estados=[self.grave.pk]), {a2.pk})
        self.assertEqual(
            pks(cursos=[self.c1a.pk, self.c1b.pk], estados=[self.grave.pk], solo_sin_revisar=True),
            set(),
        )
        self.assertEqual(
            pks(cursos=[self.c1a.pk, self.c2a.pk], estados=[self.grave.pk], solo_sin_revisar=True),
            {a4.pk},
        )

    def test_orden_curso_gravedad_porcentaje_nombre_e_id(self):
        # El curso manda sobre la gravedad y el porcentaje.
        ultima = self._caso(self.c2a, self.grave, 5, "Ana")
        beto = self._caso(self.c1b, self.leve, 60, "Beto")
        carla = self._caso(self.c1a, self.leve, 65, "Carla")
        diego = self._caso(self.c1a, self.grave, 40, "Diego")
        elena = self._caso(self.c1a, self.grave, 30, "Elena")
        fabian = self._caso(self.c1a, self.leve, 65, "Fabian")
        gabriel_1 = self._caso(self.c1a, self.leve, 65, "Gabriel")
        gabriel_2 = self._caso(self.c1a, self.leve, 65, "Gabriel")
        # Sin EstadoAlumno: porcentaje nulo, al final de su estado aunque su nombre vaya primero.
        sin_porcentaje = self._caso(self.c1a, self.leve, None, "Aaron")
        # La gravedad manda sobre el porcentaje: 10 % leve va después de los graves.
        zoe = self._caso(self.c1a, self.leve, 10, "Zoe")

        self.assertEqual(self._pks(alertas_vigentes(self.periodo)), self._pks([
            elena, diego, zoe, carla, fabian, gabriel_1, gabriel_2, sin_porcentaje, beto, ultima,
        ]))

    def test_trae_alumno_y_estado_en_la_misma_consulta(self):
        for curso in (self.c1a, self.c1b, self.c2a):
            self._caso(curso)
        with self.assertNumQueries(1):
            for alerta in alertas_vigentes(self.periodo):
                alerta.alumno.nombre, alerta.estado.nombre, alerta.curso_id, alerta.porcentaje_asistencia

    def test_devuelve_un_queryset_de_alertas(self):
        resultado = alertas_vigentes(self.periodo)
        self.assertIsInstance(resultado, QuerySet)
        self.assertEqual(resultado.model, Alerta)


class CursosMarcadosTests(ConsultasBase):
    def test_marca_con_una_alerta_y_no_con_cero(self):
        self._caso(self.c1b)
        self.assertEqual(list(cursos_marcados(self.periodo)), [self.c1b])

    def test_sin_duplicados_y_en_orden_de_nivel_y_grupo(self):
        for curso in (self.c2a, self.c1a, self.c1a, self.c1a, self.c1b):
            self._caso(curso)
        self.assertEqual(list(cursos_marcados(self.periodo)), [self.c1a, self.c1b, self.c2a])

    def test_una_revisada_marca_salvo_con_solo_sin_revisar(self):
        self._caso(self.c1a, revisada=True)
        self._caso(self.c1b)
        self.assertEqual(list(cursos_marcados(self.periodo)), [self.c1a, self.c1b])
        self.assertEqual(list(cursos_marcados(self.periodo, solo_sin_revisar=True)), [self.c1b])

    def test_cerrada_o_sin_matricula_activa_no_marca(self):
        self._caso(self.c1a, fecha_cierre=timezone.now(), motivo_cierre="recuperado")
        alumno = self._alumno()
        self._matricula(alumno, self.c1b, fecha_termino=self.hoy)
        self._alerta(alumno)
        self.assertEqual(list(cursos_marcados(self.periodo)), [])

    def test_se_restringe_con_cursos_en_alcance(self):
        for curso in (self.c1a, self.c1b, self.c2a):
            self._caso(curso)
        cargo = Cargo.objects.create(nombre="Cargo de prueba")
        rol = Rol.objects.create(nombre="Rol de prueba", alcance=Rol.ALCANCE_SELECCIONADOS)
        funcionario = Funcionario.objects.create(
            cargo=cargo, rut="9-9", nombre="Funcionario", email="funcionario@liceo.cl",
        )
        Cuenta.objects.create(funcionario=funcionario, rol=rol)
        FuncionarioCurso.objects.create(funcionario=funcionario, curso=self.c1b)
        alcance = cursos_en_alcance(funcionario, self.periodo)
        self.assertEqual(list(cursos_marcados(self.periodo, cursos=alcance)), [self.c1b])

    def test_se_restringe_con_estados(self):
        self._caso(self.c1a, self.leve)
        self._caso(self.c2a, self.grave)
        self.assertEqual(list(cursos_marcados(self.periodo, estados=[self.grave.pk])), [self.c2a])
        self.assertEqual(
            list(cursos_marcados(self.periodo, estados=Estado.objects.filter(pk=self.leve.pk))),
            [self.c1a],
        )

    def test_devuelve_un_queryset_de_cursos(self):
        self._caso(self.c1a)
        self._caso(self.c2a)
        resultado = cursos_marcados(self.periodo)
        self.assertIsInstance(resultado, QuerySet)
        self.assertEqual(resultado.model, Curso)
        self.assertEqual(list(resultado.filter(nivel=2)), [self.c2a])


class AlertasPorCursoTests(ConsultasBase):
    def test_agrupa_y_ordena_solo_cursos_con_alertas(self):
        d = self._caso(self.c2a, porcentaje=50)
        a = self._caso(self.c1a, self.grave, 50)
        b = self._caso(self.c1a, self.leve, 40)
        c = self._caso(self.c1b, porcentaje=50)
        self._curso(3, "A")  # sin alertas: no aparece

        resultado = alertas_por_curso(self.periodo)
        self.assertEqual(
            [(curso, self._pks(alertas)) for curso, alertas in resultado],
            [(self.c1a, [a.pk, b.pk]), (self.c1b, [c.pk]), (self.c2a, [d.pk])],
        )

    def test_respeta_los_filtros(self):
        self._caso(self.c1a, self.leve)
        grave = self._caso(self.c2a, self.grave)
        self._caso(self.c1b, self.grave, revisada=True)
        resultado = alertas_por_curso(self.periodo, estados=[self.grave.pk], solo_sin_revisar=True)
        self.assertEqual([(curso, self._pks(alertas)) for curso, alertas in resultado],
                         [(self.c2a, [grave.pk])])

    def test_nivel_segun_el_orden_de_umbral(self):
        medio = Estado.objects.create(nombre="Medio", umbral_minimo=40, es_no_ideal=True)
        leve = self._caso(self.c1a, self.leve)
        intermedio = self._caso(self.c1a, medio)
        grave = self._caso(self.c1a, self.grave)
        niveles = {a.pk: a.nivel for _, alertas in alertas_por_curso(self.periodo) for a in alertas}
        self.assertEqual(
            niveles, {leve.pk: "atencion", intermedio.pk: "atencion", grave.pk: "critico"},
        )

    def test_el_umbral_sale_del_catalogo_y_no_de_las_alertas_presentes(self):
        leve = self._caso(self.c1a, self.leve)  # existe un no ideal más bajo, sin alertas
        [(_, [alerta])] = alertas_por_curso(self.periodo)
        self.assertEqual((alerta.pk, alerta.nivel), (leve.pk, "atencion"))

    def test_si_hay_un_solo_no_ideal_es_critico(self):
        self.grave.delete()
        self._caso(self.c1a, self.leve)
        [(_, [alerta])] = alertas_por_curso(self.periodo)
        self.assertEqual(alerta.nivel, "critico")

    def test_sin_alertas_devuelve_lista_vacia(self):
        self.assertEqual(alertas_por_curso(self.periodo), [])
        self._caso(self.c1a, revisada=True)
        self.assertEqual(alertas_por_curso(self.periodo, solo_sin_revisar=True), [])

    def test_calcula_el_umbral_una_sola_vez(self):
        for curso in (self.c1a, self.c1a, self.c1b, self.c2a):
            self._caso(curso)
        modulo = importlib.import_module("alertas.queries.alerta_queries")
        with mock.patch.object(modulo, "umbral_critico", wraps=modulo.umbral_critico) as umbral:
            alertas_por_curso(self.periodo)
        self.assertEqual(umbral.call_count, 1)

    def _consultas(self):
        with CaptureQueriesContext(connection) as contexto:
            for curso, alertas in alertas_por_curso(self.periodo):
                curso.nivel, curso.grupo
                for alerta in alertas:
                    alerta.alumno.nombre, alerta.estado.nombre, alerta.nivel
                    alerta.curso_id, alerta.porcentaje_asistencia
        return len(contexto.captured_queries)

    def test_el_numero_de_consultas_no_crece_con_las_alertas(self):
        self._caso(self.c1a)
        self._caso(self.c1b, self.grave)
        pocas = self._consultas()
        for indice in range(30):
            self._caso((self.c1a, self.c1b, self.c2a)[indice % 3], (self.leve, self.grave)[indice % 2])
        muchas = self._consultas()
        self.assertEqual(muchas, pocas)
        self.assertLessEqual(pocas, 3)


class DePuntaAPuntaTests(ConsultasBase):
    def test_una_alerta_de_sincronizar_alerta_aparece_y_desaparece_al_recuperarse(self):
        alumno = self._alumno()
        self._matricula(alumno, self.c1b)
        estado_alumno = self._estado_alumno(alumno, Decimal("60.00"), self.leve)
        self.assertEqual(sincronizar_alerta(alumno, self.periodo), "creada")

        self.assertEqual(list(cursos_marcados(self.periodo)), [self.c1b])
        [(curso, [alerta])] = alertas_por_curso(self.periodo)
        self.assertEqual((curso, alerta.alumno, alerta.porcentaje_asistencia),
                         (self.c1b, alumno, Decimal("60.00")))

        estado_alumno.estado = self.bien
        estado_alumno.porcentaje_asistencia = Decimal("95.00")
        estado_alumno.save()
        self.assertEqual(sincronizar_alerta(alumno, self.periodo), "recuperada")
        self.assertEqual(list(cursos_marcados(self.periodo)), [])
        self.assertEqual(alertas_por_curso(self.periodo), [])


class IndependenciaTests(TestCase):
    """Los módulos nuevos no importan de monitoreo ni de asistencia, ni nombran roles o estados."""

    MODULOS = (
        "queries/periodo_queries.py",
        "queries/matricula_queries.py",
        "queries/alerta_queries.py",
        "services/niveles.py",
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
                    # Palabra completa: "críticos" (adjetivo en un docstring) no es el nombre de un estado.
                    self.assertIsNone(re.search(rf"\b{re.escape(nombre)}\b", codigo.lower()))
