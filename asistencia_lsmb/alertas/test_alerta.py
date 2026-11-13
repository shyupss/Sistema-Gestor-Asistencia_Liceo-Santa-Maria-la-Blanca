import datetime

from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Alerta, Estado
from monitoreo.services.filtro_service import (
    calcular_actividad_reciente,
    resolver_filtros_actividad_reciente,
)
from monitoreo.services.monitoreo_service import preparar_actividad_reciente


class AlertaTests(TestCase):
    def setUp(self):
        self.fecha = timezone.localdate()
        self.periodo = PeriodoAcademico.objects.create(
            anio=self.fecha.year,
            fecha_inicio=datetime.date(self.fecha.year, 1, 1),
            fecha_fin=datetime.date(self.fecha.year, 12, 31),
        )
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        vigente = EstadoMatricula.objects.create(nombre="vigente")
        self.alumno = Alumno.objects.create(nombre="Alumno Uno", rut="11111111-1")
        self.otro = Alumno.objects.create(nombre="Alumno Dos", rut="22222222-2")
        for alumno in (self.alumno, self.otro):
            Matricula.objects.create(
                alumno=alumno, curso=self.curso, periodo=self.periodo,
                estado_matricula=vigente, fecha_matricula=self.periodo.fecha_inicio,
            )
        self.estado = Estado.objects.create(
            nombre="Crítico", umbral_minimo=0, es_no_ideal=True,
        )

    def _alerta(self, alumno=None, **kwargs):
        return Alerta.objects.create(
            alumno=alumno or self.alumno, periodo=self.periodo, estado=self.estado, **kwargs
        )

    def _eventos(self, actor=None):
        qd = QueryDict(mutable=True)
        if actor:
            qd["act_actor"] = actor
        filtros = resolver_filtros_actividad_reciente(qd)
        return calcular_actividad_reciente(self.periodo, self.fecha, filtros)

    # --- autor "Sistema" ---

    def test_actividad_filtrada_muestra_alerta_con_autor_sistema(self):
        self._alerta()
        alertas = [e for e in self._eventos() if e["tipo_categoria"] == "alerta"]
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["autor"], "Sistema")
        self.assertEqual(alertas[0]["rol_autor"], "Sistema")

    def test_actividad_reciente_dashboard_muestra_alerta_con_autor_sistema(self):
        self._alerta()
        alertas = [e for e in preparar_actividad_reciente(self.fecha) if e["tipo"] == "alerta.emitida"]
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["autor"], "Sistema")
        self.assertEqual(alertas[0]["rol_autor"], "Sistema")

    # El storage con manifest de producción no tiene entradas en el entorno de test.
    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    })
    def test_ficha_del_alumno_muestra_la_alerta_como_sistema(self):
        self._alerta()
        respuesta = self.client.get(reverse("perfil_alumno", args=[self.alumno.pk]), {"tab": "alertas"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pendiente de revisión · Sistema")

    # --- filtro de actor ---

    def test_alerta_aparece_bajo_actor_sistema(self):
        self._alerta()
        tipos = {e["tipo_categoria"] for e in self._eventos("sistema")}
        self.assertIn("alerta", tipos)

    def test_alerta_no_aparece_bajo_actor_funcionario(self):
        self._alerta()
        tipos = {e["tipo_categoria"] for e in self._eventos("funcionario")}
        self.assertNotIn("alerta", tipos)

    # --- restricción de alerta vigente ---

    def test_no_permite_dos_alertas_vigentes_del_mismo_alumno_y_periodo(self):
        self._alerta()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._alerta()

    def test_permite_una_alerta_cerrada_mas_una_vigente(self):
        self._alerta(fecha_cierre=timezone.now(), motivo_cierre="recuperado")
        self._alerta()
        self.assertEqual(Alerta.objects.filter(alumno=self.alumno).count(), 2)

    def test_dos_alumnos_pueden_tener_cada_uno_su_alerta_vigente(self):
        self._alerta(self.alumno)
        self._alerta(self.otro)
        self.assertEqual(Alerta.objects.filter(fecha_cierre__isnull=True).count(), 2)
