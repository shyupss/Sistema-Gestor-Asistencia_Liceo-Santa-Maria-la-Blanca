"""Formato para mostrar: etiqueta de curso, porcentaje y nivel."""
import importlib
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import translation

from academico.models import Curso


def _formato():
    return importlib.import_module("alertas.services.formato")


class EtiquetaCursoTests(SimpleTestCase):
    def test_todos_los_niveles_y_grupos_del_sistema(self):
        # Valores literales: la misma etiqueta que muestra monitoreo ("I°A").
        esperadas = {
            (1, "A"): "I°A", (1, "B"): "I°B", (1, "C"): "I°C",
            (2, "A"): "II°A", (2, "B"): "II°B", (2, "C"): "II°C",
            (3, "A"): "III°A", (3, "B"): "III°B", (3, "C"): "III°C",
            (4, "A"): "IV°A", (4, "B"): "IV°B", (4, "C"): "IV°C",
        }
        for (nivel, grupo), etiqueta in esperadas.items():
            with self.subTest(nivel=nivel, grupo=grupo):
                self.assertEqual(_formato().etiqueta_curso(Curso(nivel=nivel, grupo=grupo)), etiqueta)

    def test_un_nivel_sin_romano_usa_el_numero(self):
        self.assertEqual(_formato().etiqueta_curso(Curso(nivel=5, grupo="A")), "5°A")


class FormatearPorcentajeTests(SimpleTestCase):
    def test_un_decimal_con_coma(self):
        casos = {
            40.5: "40,5 %",
            Decimal("62.50"): "62,5 %",
            100: "100,0 %",
            0: "0,0 %",
            Decimal("33.33"): "33,3 %",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(_formato().formatear_porcentaje(valor), esperado)

    def test_redondea_a_un_decimal_hacia_arriba_en_el_medio(self):
        casos = {66.666: "66,7 %", 40.04: "40,0 %", 40.05: "40,1 %", 12.25: "12,3 %",
                 Decimal("99.95"): "100,0 %"}
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(_formato().formatear_porcentaje(valor), esperado)

    def test_none_es_sin_datos(self):
        self.assertEqual(_formato().formatear_porcentaje(None), "sin datos")

    def test_no_depende_del_idioma_activo(self):
        for idioma in ("en", "es", "es-cl"):
            with self.subTest(idioma=idioma), translation.override(idioma):
                self.assertEqual(_formato().formatear_porcentaje(1234.56), "1234,6 %")


class FormatearNivelTests(SimpleTestCase):
    def test_etiquetas_de_los_dos_niveles(self):
        self.assertEqual(_formato().formatear_nivel("critico"), "Crítico")
        self.assertEqual(_formato().formatear_nivel("atencion"), "Atención")
