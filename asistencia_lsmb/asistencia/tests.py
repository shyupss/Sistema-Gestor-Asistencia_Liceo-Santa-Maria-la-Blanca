import datetime

from django.urls import reverse
from django.test import TestCase

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Cargo, Estado, Funcionario
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia


class ModificarAsistenciaTests(TestCase):
	def setUp(self):
		periodo = PeriodoAcademico.objects.create(
			anio=2026,
			fecha_inicio=datetime.date(2026, 3, 1),
			fecha_fin=datetime.date(2026, 12, 31),
		)
		curso = Curso.objects.create(periodo=periodo, nivel=1, grupo="A")
		estado_matricula = EstadoMatricula.objects.create(nombre="activo")
		alumno = Alumno.objects.create(nombre="Estudiante de Prueba", rut="11111111-1")
		Matricula.objects.create(
			alumno=alumno,
			curso=curso,
			periodo=periodo,
			estado_matricula=estado_matricula,
			fecha_matricula=periodo.fecha_inicio,
		)
		cargo = Cargo.objects.create(nombre="Inspector")
		funcionario = Funcionario.objects.create(
			cargo=cargo,
			rut="22222222-2",
			nombre="Inspector de Prueba",
			email="inspector@example.com",
		)
		Estado.objects.create(nombre="Crítico", umbral_minimo=0, genera_alerta=True)
		presente = Tipos_Asistencia.objects.create(nombre="Presente", cuenta_como_ausencia=False)
		ausente = Tipos_Asistencia.objects.create(nombre="Ausente", cuenta_como_ausencia=True)

		self.curso = curso
		self.alumno = alumno
		self.funcionario = funcionario
		self.presente = presente
		self.ausente = ausente
		self.fecha = datetime.date(2026, 10, 4)

	def _datos(self, presentes):
		datos = {
			"curso": self.curso.pk,
			"fecha": self.fecha.isoformat(),
			"jornada": "unica",
			"funcionario": self.funcionario.pk,
		}
		if presentes:
			datos["presentes"] = [str(self.alumno.pk)]
		return datos

	def test_post_actualiza_la_asistencia_existente(self):
		url = reverse("registrar_asistencia")

		primera_respuesta = self.client.post(url, self._datos(presentes=True))

		self.assertEqual(primera_respuesta.status_code, 302)
		self.assertEqual(Paso_Lista.objects.count(), 1)
		self.assertEqual(Asistencia_Alumnos.objects.get().tipo_asistencia, self.presente)

		segunda_respuesta = self.client.post(url, self._datos(presentes=False))

		self.assertEqual(segunda_respuesta.status_code, 302)
		self.assertEqual(Paso_Lista.objects.count(), 1)
		self.assertEqual(Asistencia_Alumnos.objects.count(), 1)
		self.assertEqual(Asistencia_Alumnos.objects.get().tipo_asistencia, self.ausente)
