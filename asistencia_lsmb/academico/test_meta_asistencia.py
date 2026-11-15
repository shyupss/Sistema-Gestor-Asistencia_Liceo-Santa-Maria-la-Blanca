import datetime
from unittest import mock

from django.test import RequestFactory, TestCase
from django.utils import timezone

from academico.models import Curso, PeriodoAcademico
from academico.perfiles_views import perfil_curso
from academico.services.academico_service import preparar_cursos
from alertas.models import ConfigGeneral


class MetaAsistenciaConfigurableTests(TestCase):
    """La meta de asistencia sale de ConfigGeneral, no de un valor fijo."""

    def setUp(self):
        self.fecha = timezone.localdate()
        self.periodo = PeriodoAcademico.objects.create(
            anio=self.fecha.year,
            fecha_inicio=datetime.date(self.fecha.year, 3, 1),
            fecha_fin=datetime.date(self.fecha.year, 12, 31),
        )
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")

    def test_resumen_de_cursos_usa_meta_configurada(self):
        _, resumen = preparar_cursos([], self.fecha, [])
        self.assertEqual(resumen["porcentaje_meta"], 75)
        ConfigGeneral.objects.filter(pk=1).update(meta_asistencia=80)
        _, resumen = preparar_cursos([], self.fecha, [])
        self.assertEqual(resumen["porcentaje_meta"], 80)

    def test_perfil_de_curso_usa_meta_configurada(self):
        ConfigGeneral.objects.filter(pk=1).update(meta_asistencia=80)
        request = RequestFactory().get("/")
        with mock.patch("academico.perfiles_views.render") as render:
            perfil_curso(request, self.curso.pk)
        contexto = render.call_args.args[2]
        self.assertEqual(contexto["porcentaje_meta"], 80)
