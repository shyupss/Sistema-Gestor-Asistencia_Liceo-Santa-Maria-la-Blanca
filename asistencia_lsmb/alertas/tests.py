from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from alertas.models import Estado


def sembrar():
    call_command("sembrar_estados", stdout=StringIO())


class SembrarEstadosTests(TestCase):
    def test_crea_los_cuatro_niveles_en_bd_vacia(self):
        sembrar()
        datos = {
            e.codigo: (e.nombre, e.umbral_minimo, e.es_no_ideal, e.genera_alerta)
            for e in Estado.objects.all()
        }
        self.assertEqual(
            datos,
            {
                "optimo": ("Óptimo", Decimal("95"), False, False),
                "adecuado": ("Adecuado", Decimal("85"), False, False),
                "atencion": ("Atención", Decimal("75"), True, True),
                "critico": ("Crítico", Decimal("0"), True, True),
            },
        )

    def test_es_idempotente(self):
        sembrar()
        sembrar()
        self.assertEqual(Estado.objects.count(), 4)

    def test_no_pisa_un_estado_existente(self):
        Estado.objects.create(
            nombre="Crítico", codigo="critico", umbral_minimo=40,
            genera_alerta=False, es_no_ideal=False,
        )
        sembrar()
        self.assertEqual(Estado.objects.count(), 4)
        critico = Estado.objects.get(codigo="critico")
        self.assertEqual(critico.umbral_minimo, Decimal("40"))
        self.assertFalse(critico.genera_alerta)
        self.assertFalse(critico.es_no_ideal)

    def test_solo_crea_los_que_faltan(self):
        Estado.objects.create(nombre="Óptimo", codigo="optimo", umbral_minimo=90)
        sembrar()
        self.assertEqual(Estado.objects.count(), 4)
        self.assertEqual(Estado.objects.get(codigo="optimo").umbral_minimo, Decimal("90"))
