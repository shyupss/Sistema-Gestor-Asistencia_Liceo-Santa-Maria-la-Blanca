from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from alertas.models import Estado


def sembrar():
    salida = StringIO()
    call_command("sembrar_estados", stdout=salida)
    return salida.getvalue()


class SembrarEstadosTests(TestCase):
    def test_crea_los_cuatro_niveles_en_bd_vacia(self):
        sembrar()
        datos = {
            e.nombre: (e.umbral_minimo, e.es_no_ideal, e.genera_alerta, e.color)
            for e in Estado.objects.all()
        }
        self.assertEqual(
            datos,
            {
                "Óptimo": (Decimal("95"), False, False, "verde"),
                "Adecuado": (Decimal("85"), False, False, "azul"),
                "Atención": (Decimal("75"), True, True, "amarillo"),
                "Crítico": (Decimal("0"), True, True, "rojo"),
            },
        )

    def test_es_idempotente(self):
        sembrar()
        salida = sembrar()
        self.assertEqual(Estado.objects.count(), 4)
        self.assertIn("Estados creados: 0", salida)

    def test_con_cualquier_estado_existente_no_crea_ni_modifica_nada(self):
        Estado.objects.create(
            nombre="Personalizado", umbral_minimo=40, genera_alerta=False,
            es_no_ideal=False, color="rojo",
        )
        salida = sembrar()
        self.assertEqual(Estado.objects.count(), 1)
        existente = Estado.objects.get()
        self.assertEqual(existente.nombre, "Personalizado")
        self.assertEqual(existente.umbral_minimo, Decimal("40"))
        self.assertFalse(existente.es_no_ideal)
        self.assertEqual(existente.color, "rojo")
        self.assertIn("Estados creados: 0", salida)


class ColorEstadoTests(TestCase):
    def _estado(self, color):
        return Estado(nombre="X", umbral_minimo=0, color=color)

    def test_full_clean_rechaza_color_fuera_de_la_lista(self):
        with self.assertRaises(ValidationError) as ctx:
            self._estado("#FF0000").full_clean()
        self.assertIn("color", ctx.exception.message_dict)

    def test_full_clean_acepta_color_valido(self):
        self._estado("verde").full_clean()

    def test_color_por_defecto_es_valido(self):
        self.assertEqual(Estado().color, "gris")
        Estado(nombre="X", umbral_minimo=0).full_clean()
