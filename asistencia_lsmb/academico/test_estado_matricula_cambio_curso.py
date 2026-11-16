import importlib

from django.apps import apps as apps_reales
from django.db import migrations
from django.test import TestCase

from academico.constantes import ESTADO_MATRICULA_CAMBIO_CURSO, ESTADOS_MATRICULA
from academico.models import EstadoMatricula

migracion_0006 = importlib.import_module("academico.migrations.0006_estados_matricula_iniciales")
migracion = importlib.import_module("academico.migrations.0007_estado_matricula_cambio_curso")

DESCRIPCION = "Matrícula cerrada porque el alumno pasó a otro curso del liceo"


def _sembrar():
    migracion.sembrar_estado_cambio_curso(apps_reales, None)


def _sembrar_0006():
    migracion_0006.sembrar_estados_matricula(apps_reales, None)


def _catalogo_de_las_migraciones():
    """Lo que dejan 0006 + 0007 sobre una tabla vacía, leído de las migraciones."""
    return {**migracion_0006.ESTADOS_MATRICULA, migracion.NOMBRE: migracion.DESCRIPCION}


def _estados_en_bd():
    return dict(EstadoMatricula.objects.values_list("nombre", "descripcion"))


class EstadoCambioCursoMigracionTests(TestCase):
    def setUp(self):
        # No se asume el contenido previo de la BD (los TransactionTestCase la vacían).
        EstadoMatricula.objects.all().delete()

    def test_crea_el_estado_con_su_descripcion(self):
        _sembrar()
        self.assertEqual(_estados_en_bd(), {"cambio_curso": DESCRIPCION})

    def test_es_idempotente(self):
        _sembrar()
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.count(), 1)
        self.assertEqual(_estados_en_bd(), {"cambio_curso": DESCRIPCION})

    def test_no_pisa_una_fila_existente_editada(self):
        _sembrar()
        EstadoMatricula.objects.filter(nombre="cambio_curso").update(descripcion="Texto editado a mano")
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.count(), 1)
        self.assertEqual(
            EstadoMatricula.objects.get(nombre="cambio_curso").descripcion, "Texto editado a mano",
        )

    def test_no_pisa_una_fila_creada_antes_de_sembrar(self):
        EstadoMatricula.objects.create(nombre="cambio_curso", descripcion=None)
        _sembrar()
        self.assertIsNone(EstadoMatricula.objects.get(nombre="cambio_curso").descripcion)
        self.assertEqual(EstadoMatricula.objects.count(), 1)

    def test_busqueda_ignora_mayusculas(self):
        existente = EstadoMatricula.objects.create(nombre="Cambio_Curso", descripcion="Antigua")
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.filter(nombre__iexact="cambio_curso").count(), 1)
        existente.refresh_from_db()
        self.assertEqual((existente.nombre, existente.descripcion), ("Cambio_Curso", "Antigua"))
        self.assertEqual(EstadoMatricula.objects.count(), 1)

    def test_no_modifica_los_otros_estados(self):
        # Dos filas editadas a mano y una ausente: solo se agrega cambio_curso.
        EstadoMatricula.objects.create(nombre="vigente", descripcion="Editada 1")
        EstadoMatricula.objects.create(nombre="Retirado", descripcion=None)
        _sembrar()
        self.assertEqual(
            _estados_en_bd(),
            {"vigente": "Editada 1", "Retirado": None, "cambio_curso": DESCRIPCION},
        )

    def test_sobre_el_catalogo_de_la_0006_deja_cuatro_estados(self):
        _sembrar_0006()
        self.assertEqual(EstadoMatricula.objects.count(), 3)
        _sembrar()
        self.assertEqual(EstadoMatricula.objects.count(), 4)
        self.assertEqual(_estados_en_bd(), _catalogo_de_las_migraciones())

    def test_el_orden_de_siembra_no_cambia_el_resultado(self):
        _sembrar()
        _sembrar_0006()
        self.assertEqual(_estados_en_bd(), _catalogo_de_las_migraciones())

    def test_no_agrega_fin_matricula(self):
        # Ese nombre es un motivo de cierre de alertas, no un estado de matrícula.
        _sembrar_0006()
        _sembrar()
        self.assertFalse(EstadoMatricula.objects.filter(nombre__iexact="fin_matricula").exists())


class EstructuraMigracion0007Tests(TestCase):
    def test_depende_de_la_0006(self):
        self.assertEqual(
            migracion.Migration.dependencies,
            [("academico", "0006_estados_matricula_iniciales")],
        )

    def test_es_solo_de_datos_y_la_reversa_no_borra(self):
        operaciones = migracion.Migration.operations
        self.assertEqual(len(operaciones), 1)
        self.assertIsInstance(operaciones[0], migrations.RunPython)
        self.assertIs(operaciones[0].code, migracion.sembrar_estado_cambio_curso)
        # Al revertir no se hace nada: no se borra ninguna fila.
        self.assertIs(operaciones[0].reverse_code, migrations.RunPython.noop)

    def test_migracion_no_importa_las_constantes_de_la_app(self):
        # Las migraciones deben quedar congeladas.
        self.assertFalse(hasattr(migracion, "constantes"))
        with open(migracion.__file__, encoding="utf-8") as archivo:
            self.assertNotIn("constantes", archivo.read())

    def test_no_repite_un_estado_de_la_0006(self):
        self.assertNotIn(migracion.NOMBRE, migracion_0006.ESTADOS_MATRICULA)


class ConstantesCoincidenConMigraciones0006y0007Tests(TestCase):
    """Las constantes de academico son exactamente lo que dejan 0006 + 0007."""

    def test_constantes_igual_a_0006_mas_0007(self):
        self.assertEqual(ESTADOS_MATRICULA, _catalogo_de_las_migraciones())

    def test_constante_suelta_de_cambio_curso(self):
        self.assertEqual(ESTADO_MATRICULA_CAMBIO_CURSO, "cambio_curso")
        self.assertEqual(ESTADO_MATRICULA_CAMBIO_CURSO, migracion.NOMBRE)
        self.assertEqual(ESTADOS_MATRICULA[ESTADO_MATRICULA_CAMBIO_CURSO], DESCRIPCION)

    def test_sembrar_0006_y_0007_deja_exactamente_las_constantes(self):
        EstadoMatricula.objects.all().delete()
        _sembrar_0006()
        _sembrar()
        self.assertEqual(_estados_en_bd(), ESTADOS_MATRICULA)

    # --- Demuestran que la comparación detecta desfases -------------------

    def test_detecta_descripcion_distinta_en_las_constantes(self):
        copia = dict(ESTADOS_MATRICULA)
        copia[ESTADO_MATRICULA_CAMBIO_CURSO] = "otra descripción"
        self.assertNotEqual(copia, _catalogo_de_las_migraciones())
        copia = dict(ESTADOS_MATRICULA)
        copia["retirado"] = "otra descripción"
        self.assertNotEqual(copia, _catalogo_de_las_migraciones())

    def test_detecta_estado_quitado_de_las_constantes(self):
        copia = dict(ESTADOS_MATRICULA)
        del copia[ESTADO_MATRICULA_CAMBIO_CURSO]
        self.assertNotEqual(copia, _catalogo_de_las_migraciones())

    def test_detecta_estado_agregado_a_las_constantes(self):
        copia = dict(ESTADOS_MATRICULA)
        copia["nuevo"] = "Un estado que ninguna migración siembra"
        self.assertNotEqual(copia, _catalogo_de_las_migraciones())

    def test_detecta_que_la_0006_sola_ya_no_alcanza(self):
        # Sin la 0007 las constantes tendrían un estado que ninguna migración siembra.
        self.assertNotEqual(ESTADOS_MATRICULA, migracion_0006.ESTADOS_MATRICULA)
