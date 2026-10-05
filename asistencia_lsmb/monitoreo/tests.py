import datetime
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Alerta, Cargo, Estado, Funcionario
from asistencia.models import Estados_Solicitud, Justificaciones, Paso_Lista
from monitoreo.services.monitoreo_service import (
	preparar_actividad_reciente,
	preparar_justificaciones,
)


class MonitoreoOperativoTests(TestCase):
	def setUp(self):
		self.fecha = datetime.date(2026, 10, 5)
		self.periodo = PeriodoAcademico.objects.create(
			anio=2026,
			fecha_inicio=datetime.date(2026, 3, 1),
			fecha_fin=datetime.date(2026, 12, 31),
		)
		self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
		estado_matricula = EstadoMatricula.objects.create(nombre="activo")
		self.alumno = Alumno.objects.create(nombre="Estudiante de Monitoreo", rut="12345678-5")
		Matricula.objects.create(
			alumno=self.alumno,
			curso=self.curso,
			periodo=self.periodo,
			estado_matricula=estado_matricula,
			fecha_matricula=self.periodo.fecha_inicio,
		)
		cargo = Cargo.objects.create(nombre="Inspectoría")
		self.funcionario = Funcionario.objects.create(
			cargo=cargo,
			rut="98765432-1",
			nombre="Inspector de Monitoreo",
			email="inspector@ejemplo.cl",
		)
		self.estado_alerta = Estado.objects.create(
			nombre="Crítico",
			umbral_minimo=0,
			genera_alerta=True,
		)
		self.estado_pendiente = Estados_Solicitud.objects.create(nombre="pendiente")
		self.estado_aceptada = Estados_Solicitud.objects.create(
			nombre="aceptada",
			es_estado_final=True,
			cubre_ausencia=True,
		)

	def test_muestra_pendientes_y_promedio_de_resolucion(self):
		ahora = timezone.now()
		Justificaciones.objects.create(
			alumno=self.alumno,
			estado_solicitud=self.estado_pendiente,
			fecha_inicio=self.fecha,
			fecha_fin=self.fecha,
			resumen="Control médico",
		)
		resuelta = Justificaciones.objects.create(
			alumno=self.alumno,
			estado_solicitud=self.estado_aceptada,
			fecha_inicio=self.fecha,
			fecha_fin=self.fecha,
			resumen="Certificado médico",
			funcionario_resuelve=self.funcionario,
		)
		resuelta.fecha_registro = ahora - timedelta(days=2)
		resuelta.fecha_resolucion = ahora - timedelta(days=1)
		resuelta.save(update_fields=["fecha_registro", "fecha_resolucion"])

		datos = preparar_justificaciones(self.fecha)

		self.assertEqual(datos["pendientes_count"], 1)
		self.assertEqual(datos["justificaciones_pendientes"][0]["motivo"], "Control médico")
		self.assertEqual(datos["prom_resolucion"], "1.0 días")

	def test_actividad_reciente_usa_registros_reales(self):
		Paso_Lista.objects.create(
			curso=self.curso,
			funcionario=self.funcionario,
			fecha=self.fecha,
		)
		Justificaciones.objects.create(
			alumno=self.alumno,
			estado_solicitud=self.estado_pendiente,
			fecha_inicio=self.fecha,
			fecha_fin=self.fecha,
			resumen="Control médico",
		)
		Alerta.objects.create(
			alumno=self.alumno,
			periodo=self.periodo,
			estado=self.estado_alerta,
			funcionario=self.funcionario,
		)

		eventos = preparar_actividad_reciente(self.fecha)
		tipos = {evento["tipo"] for evento in eventos}

		self.assertIn("asistencia.registrada", tipos)
		self.assertIn("justificacion.nueva", tipos)
		self.assertIn("alerta.emitida", tipos)
