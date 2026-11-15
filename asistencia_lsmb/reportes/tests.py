import datetime

from django.test import TestCase
from django.urls import reverse

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Cargo, Funcionario
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia


class VistaPreviaReportesTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=datetime.date(2026, 3, 1),
            fecha_fin=datetime.date(2026, 12, 31),
        )
        self.curso_a = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.curso_b = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="B")
        estado = EstadoMatricula.objects.create(nombre="vigente")
        alumno = Alumno.objects.create(nombre="Estudiante", rut="11111111-1")
        Matricula.objects.create(
            alumno=alumno,
            curso=self.curso_a,
            periodo=self.periodo,
            estado_matricula=estado,
            fecha_matricula=self.periodo.fecha_inicio,
        )
        funcionario = Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Inspector"),
            rut="22222222-2",
            nombre="Inspector",
            email="inspector-reportes@example.com",
        )
        tipo = Tipos_Asistencia.objects.create(nombre="Presente", cuenta_como_ausencia=False)
        paso = Paso_Lista.objects.create(
            curso=self.curso_a,
            funcionario=funcionario,
            fecha=datetime.date(2026, 4, 1),
        )
        Asistencia_Alumnos.objects.create(
            alumno=alumno,
            paso_lista=paso,
            tipo_asistencia=tipo,
        )

    def test_aplica_periodo_semestre_y_curso_en_la_vista_previa(self):
        respuesta = self.client.get(
            reverse("reportes"),
            {"anio": "2026", "semestre": "1", "curso": str(self.curso_a.pk)},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["indicadores"][3][1], "1")
        self.assertEqual(respuesta.context["filas"][0][0], "I°A")
        self.assertEqual(len(respuesta.context["filas"]), 1)

    def test_semestre_sin_registros_muestra_cursos_sin_datos(self):
        respuesta = self.client.get(
            reverse("reportes"),
            {"anio": "2026", "semestre": "2", "curso": str(self.curso_a.pk)},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["indicadores"][3][1], "0")
        self.assertEqual(respuesta.context["filas"][0][-1], "Sin datos")

# Create your tests here.
