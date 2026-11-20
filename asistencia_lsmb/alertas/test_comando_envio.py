"""Comando enviar_resumenes_alertas: --dry-run, --to y --enviar, con --email y --hoy."""
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from alertas.models import Notificacion, NotificacionCurso
from alertas.test_envio_alertas import BackendQueFalla, EnvioBase
from alertas.test_resumen_alertas import UN_DIA


class ComandoEnvioTests(EnvioBase):
    """Escenario de EnvioBase: Ana con 9 alumnos en 2 cursos y Otro sin contenido."""

    def _comando(self, *args):
        salida = StringIO()
        call_command("enviar_resumenes_alertas", *args, stdout=salida)
        return salida.getvalue()

    def test_sin_modo_da_error(self):
        with self.assertRaisesMessage(CommandError, "exactamente un modo"):
            self._comando()

    def test_dos_modos_dan_error(self):
        for args in (("--dry-run", "--enviar"), ("--dry-run", "--to", "x@example.cl"),
                     ("--to", "x@example.cl", "--enviar")):
            with self.subTest(args=args), self.assertRaisesMessage(CommandError, "exactamente un modo"):
                self._comando(*args)
        self.assertEqual(mail.outbox, [])

    def test_dry_run_imprime_y_no_envia_ni_registra_ni_conecta(self):
        with mock.patch("django.core.mail.get_connection", side_effect=AssertionError("conectó")):
            salida = self._comando("--dry-run")
        self.assertIn(f"Para: Ana Funcionaria <{self.ana.email}>", salida)
        self.assertIn("Asunto: Alertas de asistencia: 9 alumnos en 2 cursos", salida)
        self.assertIn("Hola, Ana Funcionaria", salida)
        self.assertIn("Beto", salida)
        self.assertNotIn("Otro Funcionario", salida)
        self.assertEqual(salida.splitlines()[-1], "Generados: 1. Sin correo: 0. Sin contenido: 1.")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Notificacion.objects.exists())

    def test_to_entrega_a_esa_direccion_y_no_registra(self):
        salida = self._comando("--to", "pruebas@example.cl")
        [mensaje] = mail.outbox
        self.assertEqual(mensaje.to, ["pruebas@example.cl"])
        self.assertTrue(mensaje.subject.startswith(f"[PRUEBA para {self.ana.email}] "))
        self.assertFalse(Notificacion.objects.exists())
        self.assertEqual(salida.splitlines()[-1], "Enviados: 1. Fallidos: 0. Sin correo: 0. Sin contenido: 1.")

    def test_to_con_correo_invalido_da_error(self):
        with self.assertRaisesMessage(CommandError, "no es un correo válido"):
            self._comando("--to", "no-es-correo")

    def test_enviar_entrega_a_los_reales_y_registra(self):
        salida = self._comando("--enviar")
        self.assertEqual([m.to for m in mail.outbox], [[self.ana.email]])
        self.assertFalse(mail.outbox[0].subject.startswith("[PRUEBA"))
        notificacion = Notificacion.objects.get()
        self.assertEqual(notificacion.funcionario, self.ana)
        self.assertEqual(
            set(NotificacionCurso.objects.values_list("curso_id", flat=True)), {self.c1a.pk, self.c2a.pk},
        )
        self.assertEqual(salida.splitlines()[-1], "Enviados: 1. Fallidos: 0. Sin correo: 0. Sin contenido: 1.")

    def test_email_filtra(self):
        salida = self._comando("--enviar", "--email", self.ana.email.upper())
        self.assertEqual(salida.splitlines()[-1], "Enviados: 1. Fallidos: 0. Sin correo: 0. Sin contenido: 0.")
        salida = self._comando("--dry-run", "--email", self.otro.email)
        self.assertEqual(salida.splitlines()[-1], "Generados: 0. Sin correo: 0. Sin contenido: 1.")
        self.assertEqual(len(mail.outbox), 1)

    def test_correo_inexistente_o_que_no_es_destinatario_da_error(self):
        sin_permiso = self._funcionario(self._rol("Rol sin permiso", recibe_todos=True, con_permiso=False))
        with self.assertRaisesMessage(CommandError, "No existe ningún funcionario con el correo nadie@liceo.cl"):
            self._comando("--enviar", "--email", "nadie@liceo.cl")
        with self.assertRaisesMessage(CommandError, f"{sin_permiso.email} no es destinatario"):
            self._comando("--enviar", "--email", sin_permiso.email)
        self.assertEqual(mail.outbox, [])

    def test_hoy_cambia_el_resultado(self):
        salida = self._comando("--dry-run", "--hoy", "1990-06-01")
        self.assertIn("No hay período académico para el año 1990.", salida)
        self.assertEqual(salida.splitlines()[-1], "Generados: 0. Sin correo: 0. Sin contenido: 2.")
        # Con hoy = mañana, la matrícula de un alumno que termina mañana ya no cuenta.
        self._caso(self.c1b, self.grave, 10, "Dario", fecha_termino=self.hoy + UN_DIA)
        self.assertIn("Dario", self._comando("--dry-run"))
        self.assertNotIn("Dario", self._comando("--dry-run", "--hoy", (self.hoy + UN_DIA).isoformat()))

    @override_settings(EMAIL_BACKEND="alertas.test_envio_alertas.BackendQueFalla")
    def test_con_fallidos_el_codigo_de_salida_no_es_cero(self):
        BackendQueFalla.fallan = {self.ana.email, "pruebas@example.cl"}
        for args in (("--enviar",), ("--to", "pruebas@example.cl")):
            salida = StringIO()
            with self.subTest(args=args), self.assertLogs("alertas.services.envio_alertas", "ERROR"), \
                    self.assertRaises(CommandError) as error:
                call_command("enviar_resumenes_alertas", *args, stdout=salida)
            self.assertNotEqual(error.exception.returncode, 0)
            self.assertIn("Enviados: 0. Fallidos: 1.", salida.getvalue())
        self.assertFalse(Notificacion.objects.exists())
