import datetime

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from academico.models import Curso, PeriodoAcademico
from alertas.models import Cargo, Funcionario
from asistencia.models import Paso_Lista


class PasoListaUnicoPorCursoYFechaTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=datetime.date(2026, 3, 1),
            fecha_fin=datetime.date(2026, 12, 31),
        )
        self.curso_a = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.curso_b = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="B")
        cargo = Cargo.objects.create(nombre="Inspector")
        self.funcionario = Funcionario.objects.create(
            cargo=cargo, rut="22222222-2", nombre="Inspector", email="i@example.com"
        )
        self.dia = datetime.date(2026, 4, 10)

    def _paso(self, curso, fecha):
        return Paso_Lista.objects.create(curso=curso, funcionario=self.funcionario, fecha=fecha)

    def test_no_permite_dos_listas_el_mismo_dia_para_el_mismo_curso(self):
        self._paso(self.curso_a, self.dia)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._paso(self.curso_a, self.dia)

    def test_permite_el_mismo_curso_en_dias_distintos(self):
        self._paso(self.curso_a, self.dia)
        self._paso(self.curso_a, self.dia + datetime.timedelta(days=1))
        self.assertEqual(Paso_Lista.objects.count(), 2)

    def test_permite_dos_cursos_distintos_el_mismo_dia(self):
        self._paso(self.curso_a, self.dia)
        self._paso(self.curso_b, self.dia)
        self.assertEqual(Paso_Lista.objects.count(), 2)


class MigracionSinJornadaTests(TransactionTestCase):
    """La migración 0004 aborta con un mensaje claro si hay duplicados (curso, fecha)."""

    migrar_hasta = [("asistencia", "0004_paso_lista_sin_jornada")]

    @staticmethod
    def _destino_previo():
        """Último estado de todas las apps, salvo asistencia, que queda en 0003."""
        hojas = MigrationExecutor(connection).loader.graph.leaf_nodes()
        return [n for n in hojas if n[0] != "asistencia"] + [
            ("asistencia", "0003_justificaciones_fecha_registro")
        ]

    def _migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def _restaurar_ultimo_estado(self):
        # Siempre deja la BD de test en el último estado de migraciones. Los pasos
        # duplicados creados por el test se borran antes, o 0004 volvería a abortar.
        if getattr(self, "_paso_historico", None) is not None:
            self._paso_historico.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_aborta_con_mensaje_claro_si_hay_duplicados(self):
        self.addCleanup(self._restaurar_ultimo_estado)
        apps = self._migrar(self._destino_previo())

        Periodo = apps.get_model("academico", "PeriodoAcademico")
        Curso = apps.get_model("academico", "Curso")
        Cargo = apps.get_model("alertas", "Cargo")
        Funcionario = apps.get_model("alertas", "Funcionario")
        Paso = apps.get_model("asistencia", "Paso_Lista")
        self._paso_historico = Paso

        periodo = Periodo.objects.create(
            anio=2026, fecha_inicio=datetime.date(2026, 3, 1), fecha_fin=datetime.date(2026, 12, 31)
        )
        curso = Curso.objects.create(periodo=periodo, nivel=1, grupo="A")
        cargo = Cargo.objects.create(nombre="Inspector")
        funcionario = Funcionario.objects.create(
            cargo=cargo, rut="22222222-2", nombre="Inspector", email="i@example.com"
        )
        dia = datetime.date(2026, 4, 10)
        Paso.objects.create(curso=curso, funcionario=funcionario, fecha=dia, jornada="manana")
        Paso.objects.create(curso=curso, funcionario=funcionario, fecha=dia, jornada="tarde")

        with self.assertRaises(RuntimeError) as ctx:
            self._migrar(self.migrar_hasta)

        mensaje = str(ctx.exception)
        self.assertIn("duplicados por (curso, fecha)", mensaje)
        self.assertIn(f"curso {curso.pk} / {dia}", mensaje)
        self.assertIn("manana, tarde", mensaje)

        # No quedó aplicada: la columna sigue existiendo.
        executor = MigrationExecutor(connection)
        self.assertNotIn(self.migrar_hasta[0], executor.loader.applied_migrations)
