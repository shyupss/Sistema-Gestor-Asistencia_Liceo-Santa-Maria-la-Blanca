"""Comando resumen_alertas: solo lectura, muestra qué recibiría cada destinatario."""
import datetime
from decimal import Decimal
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError

from alertas.models import Alerta, Notificacion, Rol
from alertas.test_resumen_alertas import UN_DIA, ResumenBase


class ComandoResumenAlertasTests(ResumenBase):
    """Escenario: un destinatario con contenido, uno sin contenido y uno sin permiso."""

    def setUp(self):
        super().setUp()
        self.general = self._funcionario(
            self._rol("Rol general", recibe_todos=True), nombre="Ana Funcionaria",
        )
        self.sin_contenido = self._funcionario(
            self._rol("Rol asignado", estados=[self.leve, self.grave]), nombre="Otro Funcionario",
        )
        self.sin_permiso = self._funcionario(
            self._rol("Rol sin permiso", Rol.ALCANCE_TODOS, recibe_todos=True, con_permiso=False),
        )
        self._caso(self.c1a, self.grave, Decimal("40.50"), "Beto",
                   fecha_termino=self.hoy + UN_DIA)
        self._caso(self.c1a, self.leve, None, "Carla")
        for indice in range(7):
            self._caso(self.c2a, self.leve, 50 + indice, f"Alumno {indice + 1}")

    def _comando(self, *args):
        salida = StringIO()
        call_command("resumen_alertas", *args, stdout=salida)
        return salida.getvalue().splitlines()

    def _fecha(self):
        return self.hoy.strftime("%d/%m/%Y")

    def test_imprime_lo_esperado(self):
        fecha = self._fecha()
        alumnos_2a = [
            f"    - Alumno {n} · Leve · {49 + n:.1f} % · alerta del {fecha}" for n in range(1, 6)
        ]
        self.assertEqual(self._comando(), [
            f"Resumen de alertas al {fecha} (período {self.periodo.anio}). "
            "Solo lectura: no se envía nada.",
            "",
            "Ana Funcionaria <funcionario1@liceo.cl> — rol: Rol general",
            "  1°A, 2 alumnos",
            f"    - Beto · Grave · 40.5 % · alerta del {fecha}",
            f"    - Carla · Leve · sin datos · alerta del {fecha}",
            "  2°A, 7 alumnos",
            *alumnos_2a,
            "    ... y 2 más",
            "",
            "Destinatarios con contenido: 1. Sin contenido: 1.",
        ])

    def test_email_filtra_sin_distinguir_mayusculas(self):
        salida = self._comando("--email", "  FUNCIONARIO1@Liceo.CL ")
        self.assertIn("Ana Funcionaria <funcionario1@liceo.cl> — rol: Rol general", salida)
        self.assertEqual(salida[-1], "Destinatarios con contenido: 1. Sin contenido: 0.")

        salida = self._comando("--email", self.sin_contenido.email)
        self.assertNotIn("Ana Funcionaria <funcionario1@liceo.cl> — rol: Rol general", salida)
        self.assertEqual(salida[-1], "Destinatarios con contenido: 0. Sin contenido: 1.")

    def test_correo_inexistente_o_que_no_es_destinatario_da_error_claro(self):
        with self.assertRaisesMessage(CommandError, "No existe ningún funcionario con el correo nadie@liceo.cl"):
            self._comando("--email", "nadie@liceo.cl")
        with self.assertRaisesMessage(CommandError, f"{self.sin_permiso.email} no es destinatario"):
            self._comando("--email", self.sin_permiso.email)

    def test_hoy_cambia_el_resultado(self):
        # Con hoy = mañana, la matrícula de Beto ya terminó.
        manana = self.hoy + UN_DIA
        salida = self._comando("--hoy", manana.isoformat())
        self.assertFalse(any("Beto" in linea for linea in salida))
        self.assertTrue(any("Carla" in linea for linea in salida) or manana.year != self.hoy.year)

        sin_periodo = self._comando("--hoy", "1990-06-01")
        self.assertEqual(sin_periodo, [
            "Resumen de alertas al 01/06/1990: no hay período académico para el año 1990.",
            "",
            "Destinatarios con contenido: 0. Sin contenido: 2.",
        ])

    def test_hoy_invalido_da_error(self):
        with self.assertRaises(CommandError):
            self._comando("--hoy", "20-11-2026")

    def test_no_cambia_ninguna_tabla(self):
        def conteos():
            return {modelo._meta.label: modelo.objects.count() for modelo in apps.get_models()}

        antes = conteos()
        self._comando()
        self._comando("--email", self.general.email)
        self._comando("--hoy", (self.hoy - 10 * UN_DIA).isoformat())
        self.assertEqual(conteos(), antes)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(Alerta.objects.count(), 9)
