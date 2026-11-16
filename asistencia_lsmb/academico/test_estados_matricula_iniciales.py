import importlib

from django.apps import apps as apps_reales
from django.test import TestCase

from academico.constantes import ESTADOS_MATRICULA
from academico.models import EstadoMatricula

migracion = importlib.import_module("academico.migrations.0006_estados_matricula_iniciales")


def _sembrar():
    migracion.sembrar_estados_matricula(apps_reales, None)


class EstadosMatriculaInicialesTests(TestCase):
    def setUp(self):
        # No se asume el contenido previo de la BD (los TransactionTestCase la vacían).
        EstadoMatricula.objects.all().delete()

    def test_crea_los_tres_estados_con_sus_descripciones(self):
        _sembrar()
        self.assertEqual(
            dict(EstadoMatricula.objects.values_list("nombre", "descripcion")),
            {
                "vigente": "Alumno con matrícula vigente",
                "retirado": "Alumno que se retiró del liceo",
                "egresado": "Alumno que egresó del liceo",
            },
        )

    def test_es_idempotente(self):
        _sembrar()
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.count(), 3)

    def test_no_pisa_una_fila_existente_editada(self):
        _sembrar()
        EstadoMatricula.objects.filter(nombre="retirado").update(descripcion="Texto editado a mano")
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.count(), 3)
        self.assertEqual(
            EstadoMatricula.objects.get(nombre="retirado").descripcion, "Texto editado a mano",
        )

    def test_no_pisa_una_fila_creada_antes_de_sembrar(self):
        EstadoMatricula.objects.get_or_create(nombre="egresado", defaults={"descripcion": None})
        _sembrar()
        self.assertIsNone(EstadoMatricula.objects.get(nombre="egresado").descripcion)
        self.assertEqual(EstadoMatricula.objects.count(), 3)

    def test_busqueda_ignora_mayusculas(self):
        existente = EstadoMatricula.objects.get_or_create(
            nombre="Vigente", defaults={"descripcion": "Antigua"},
        )[0]
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.filter(nombre__iexact="vigente").count(), 1)
        existente.refresh_from_db()
        self.assertEqual((existente.nombre, existente.descripcion), ("Vigente", "Antigua"))
        self.assertEqual(EstadoMatricula.objects.count(), 3)

    def test_coincide_con_las_constantes_de_academico(self):
        self.assertEqual(migracion.ESTADOS_MATRICULA, ESTADOS_MATRICULA)
        _sembrar()
        self.assertEqual(
            dict(EstadoMatricula.objects.values_list("nombre", "descripcion")), ESTADOS_MATRICULA,
        )

    def test_migracion_no_importa_las_constantes_de_la_app(self):
        # Las migraciones deben quedar congeladas.
        self.assertFalse(hasattr(migracion, "constantes"))
        with open(migracion.__file__, encoding="utf-8") as archivo:
            self.assertNotIn("constantes", archivo.read())
