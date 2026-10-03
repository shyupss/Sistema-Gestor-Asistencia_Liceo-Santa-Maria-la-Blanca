"""
Pruebas automatizadas — H13: Gestionar los alumnos del colegio
(cambios de cursos, de colegio, etc.)

Cobertura:
  - Creación y validación de Alumno (RUT único, normalización)
  - Edición de datos básicos de un alumno
  - Matrícula activa única por periodo (no duplicados simultáneos)
  - Cambio de curso: cierre de matrícula anterior y apertura de una nueva
  - Retiro del colegio: matrícula con fecha_termino y estado "retirado"
"""

# test unitario automatizado de caja blanca, escritos sobre Django TestCase con BD en memoria,
# que verifican reglas de negocio y restricciones de integridad del módulo académico (H13).

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from academico.models import (
    Alumno,
    Curso,
    EstadoMatricula,
    Matricula,
    PeriodoAcademico,
    normalizar_rut,
)


# ---------------------------------------------------------------------------
# Fixture base reutilizable
# ---------------------------------------------------------------------------

class BaseAlumnoTestCase(TestCase):
    """Crea los objetos mínimos compartidos por todas las pruebas."""

    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=datetime.date(2026, 3, 1),
            fecha_fin=datetime.date(2026, 12, 31),
        )
        self.curso_1a = Curso.objects.create(
            periodo=self.periodo,
            nivel=1,
            grupo="A",
        )
        self.curso_1b = Curso.objects.create(
            periodo=self.periodo,
            nivel=1,
            grupo="B",
        )
        self.estado_activo = EstadoMatricula.objects.create(
            nombre="activo",
            descripcion="Alumno con matrícula vigente",
        )
        self.estado_retirado = EstadoMatricula.objects.create(
            nombre="retirado",
            descripcion="Alumno retirado del colegio",
        )


# ---------------------------------------------------------------------------
# 1. Normalización del RUT
# ---------------------------------------------------------------------------

class NormalizacionRutTests(TestCase):
    """Verifica que la función normalizar_rut produce el formato correcto."""

    def test_rut_con_puntos_y_guion(self):
        self.assertEqual(normalizar_rut("12.345.678-9"), "12345678-9")

    def test_rut_sin_formato(self):
        self.assertEqual(normalizar_rut("123456789"), "12345678-9")

    def test_rut_con_k_minuscula(self):
        self.assertEqual(normalizar_rut("12345678-k"), "12345678-K")

    def test_rut_vacio(self):
        self.assertEqual(normalizar_rut(""), "")

    def test_rut_none(self):
        self.assertEqual(normalizar_rut(None), "")


# ---------------------------------------------------------------------------
# 2. Creación de Alumno
# ---------------------------------------------------------------------------

class CreacionAlumnoTests(TestCase):
    """Verifica las reglas de negocio al crear un nuevo alumno."""

    def test_crear_alumno_valido(self):
        alumno = Alumno.objects.create(nombre="Juan Pérez", rut="12345678-9")
        self.assertIsNotNone(alumno.pk)

    def test_rut_se_normaliza_al_guardar(self):
        alumno = Alumno.objects.create(nombre="Ana García", rut="12.345.678-9")
        self.assertEqual(alumno.rut, "12345678-9")

    def test_rut_duplicado_lanza_excepcion(self):
        Alumno.objects.create(nombre="Pedro López", rut="11111111-1")
        with self.assertRaises(ValidationError):
            Alumno.objects.create(nombre="Otro Alumno", rut="11111111-1")

    def test_rut_duplicado_con_distinto_formato_lanza_excepcion(self):
        """El mismo RUT escrito con puntos no debe poder registrarse dos veces."""
        Alumno.objects.create(nombre="Pedro López", rut="11111111-1")
        with self.assertRaises(ValidationError):
            Alumno.objects.create(nombre="Otro Alumno", rut="11.111.111-1")


# ---------------------------------------------------------------------------
# 3. Edición de datos de un Alumno
# ---------------------------------------------------------------------------

class EdicionAlumnoTests(TestCase):
    """Verifica que se pueden actualizar los datos básicos de un alumno."""

    def setUp(self):
        self.alumno = Alumno.objects.create(
            nombre="Carlos Soto",
            rut="22222222-2",
            email="carlos@example.com",
        )

    def test_editar_nombre(self):
        self.alumno.nombre = "Carlos Soto Rojas"
        self.alumno.save()
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.nombre, "Carlos Soto Rojas")

    def test_editar_email(self):
        self.alumno.email = "nuevo@example.com"
        self.alumno.save()
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.email, "nuevo@example.com")

    def test_editar_telefono(self):
        self.alumno.telefono = "+56912345678"
        self.alumno.save()
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.telefono, "+56912345678")


# ---------------------------------------------------------------------------
# 4. Matrícula activa única por periodo
# ---------------------------------------------------------------------------

class MatriculaActivaUnicaTests(BaseAlumnoTestCase):
    """
    Un alumno no puede tener dos matrículas activas (sin fecha_termino)
    en el mismo periodo.
    """

    def setUp(self):
        super().setUp()
        self.alumno = Alumno.objects.create(nombre="María Núñez", rut="33333333-3")

    def test_crear_matricula_valida(self):
        m = Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=datetime.date(2026, 3, 1),
        )
        self.assertIsNotNone(m.pk)

    def test_dos_matriculas_activas_mismo_periodo_falla(self):
        """
        El UniqueConstraint 'uq_matricula_alumno_periodo_vigente' impide
        que existan dos filas con fecha_termino=NULL para el mismo alumno y periodo.
        """
        Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=datetime.date(2026, 3, 1),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Matricula.objects.create(
                alumno=self.alumno,
                curso=self.curso_1b,
                periodo=self.periodo,
                estado_matricula=self.estado_activo,
                fecha_matricula=datetime.date(2026, 3, 1),
            )


# ---------------------------------------------------------------------------
# 5. Cambio de curso
# ---------------------------------------------------------------------------

class CambioCursoTests(BaseAlumnoTestCase):
    """
    Simula el flujo de cambio de curso:
      1. Alumno comienza en Curso 1A.
      2. Se cierra esa matrícula (fecha_termino).
      3. Se abre una nueva matrícula en Curso 1B.
    """

    def setUp(self):
        super().setUp()
        self.alumno = Alumno.objects.create(nombre="Luis Vera", rut="44444444-4")
        self.matricula_original = Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=datetime.date(2026, 3, 1),
        )

    def test_cambio_de_curso_exitoso(self):
        fecha_cambio = datetime.date(2026, 6, 1)

        # Paso 1: cerrar matrícula actual
        self.matricula_original.fecha_termino = fecha_cambio
        self.matricula_original.save()

        # Paso 2: crear matrícula en nuevo curso
        nueva_matricula = Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1b,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=fecha_cambio,
        )

        # Verificar que el alumno ahora está en el curso 1B
        self.assertEqual(nueva_matricula.curso, self.curso_1b)

    def test_matricula_anterior_queda_cerrada(self):
        fecha_cambio = datetime.date(2026, 6, 1)
        self.matricula_original.fecha_termino = fecha_cambio
        self.matricula_original.save()

        self.matricula_original.refresh_from_db()
        self.assertIsNotNone(self.matricula_original.fecha_termino)

    def test_solo_una_matricula_activa_tras_cambio(self):
        fecha_cambio = datetime.date(2026, 6, 1)
        self.matricula_original.fecha_termino = fecha_cambio
        self.matricula_original.save()

        Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1b,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=fecha_cambio,
        )

        activas = Matricula.objects.filter(
            alumno=self.alumno,
            periodo=self.periodo,
            fecha_termino__isnull=True,
        )
        self.assertEqual(activas.count(), 1)


# ---------------------------------------------------------------------------
# 6. Retiro del colegio (cambio de colegio)
# ---------------------------------------------------------------------------

class RetiroAlumnoTests(BaseAlumnoTestCase):
    """
    Simula el retiro de un alumno:
      - Se cierra la matrícula con fecha_termino.
      - El estado cambia a "retirado".
    """

    def setUp(self):
        super().setUp()
        self.alumno = Alumno.objects.create(nombre="Sofía Ramos", rut="55555555-5")
        self.matricula = Matricula.objects.create(
            alumno=self.alumno,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_activo,
            fecha_matricula=datetime.date(2026, 3, 1),
        )

    def test_retiro_cierra_matricula(self):
        fecha_retiro = datetime.date(2026, 8, 15)
        self.matricula.fecha_termino = fecha_retiro
        self.matricula.estado_matricula = self.estado_retirado
        self.matricula.save()

        self.matricula.refresh_from_db()
        self.assertEqual(self.matricula.fecha_termino, fecha_retiro)
        self.assertEqual(self.matricula.estado_matricula.nombre, "retirado")

    def test_alumno_retirado_no_tiene_matricula_activa(self):
        self.matricula.fecha_termino = datetime.date(2026, 8, 15)
        self.matricula.estado_matricula = self.estado_retirado
        self.matricula.save()

        activas = Matricula.objects.filter(
            alumno=self.alumno,
            periodo=self.periodo,
            fecha_termino__isnull=True,
        )
        self.assertEqual(activas.count(), 0)

    def test_alumno_permanece_en_bd_tras_retiro(self):
        """Retirar a un alumno NO debe eliminarlo del sistema."""
        self.matricula.fecha_termino = datetime.date(2026, 8, 15)
        self.matricula.estado_matricula = self.estado_retirado
        self.matricula.save()

        self.assertTrue(Alumno.objects.filter(pk=self.alumno.pk).exists())
