import datetime
import shutil
import tempfile
from io import BytesIO

from openpyxl import load_workbook
from django.test import TestCase
from django.urls import reverse

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Cargo, Funcionario
from asistencia.models import (
    Asistencia_Alumnos,
    Estados_Solicitud,
    Justificaciones,
    Paso_Lista,
    Tipos_Asistencia,
)
from reportes.models import ReporteGenerado


class VistaPreviaReportesTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=datetime.date(2026, 3, 1),
            fecha_fin=datetime.date(2026, 12, 31),
        )
        self.curso_a = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.curso_b = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="B")
        estado = EstadoMatricula.objects.get_or_create(nombre="vigente")[0]
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

    def test_ausencia_justificada_no_se_cuenta_como_ausencia(self):
        alumno = Matricula.objects.get(curso=self.curso_a).alumno
        funcionario = Paso_Lista.objects.get(curso=self.curso_a).funcionario
        tipo_ausente = Tipos_Asistencia.objects.create(
            nombre="Ausente",
            cuenta_como_ausencia=True,
        )
        estado_cubre = Estados_Solicitud.objects.create(
            nombre="Aprobada",
            cubre_ausencia=True,
        )
        justificacion = Justificaciones.objects.create(
            alumno=alumno,
            funcionario_resuelve=funcionario,
            estado_solicitud=estado_cubre,
            fecha_inicio=datetime.date(2026, 4, 2),
            fecha_fin=datetime.date(2026, 4, 2),
            resumen="Justificación de prueba",
        )
        paso = Paso_Lista.objects.create(
            curso=self.curso_a,
            funcionario=funcionario,
            fecha=datetime.date(2026, 4, 2),
        )
        Asistencia_Alumnos.objects.create(
            alumno=alumno,
            paso_lista=paso,
            tipo_asistencia=tipo_ausente,
            justificacion=justificacion,
        )

        respuesta = self.client.get(
            reverse("reportes"),
            {"anio": "2026", "semestre": "1", "curso": str(self.curso_a.pk)},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["indicadores"][1][1], "0")
        self.assertEqual(respuesta.context["indicadores"][0][1], "100.0%")

    def test_generar_planilla_excel_crea_archivo_e_historial(self):
        media_root = tempfile.mkdtemp()
        try:
            with self.settings(MEDIA_ROOT=media_root):
                respuesta = self.client.post(
                    reverse("generar_reporte"),
                    {
                        "reporte": "planilla",
                        "formato": "Excel",
                        "anio": "2026",
                        "semestre": "1",
                        "curso": str(self.curso_a.pk),
                    },
                )

                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(
                    "application/vnd.openxmlformats-officedocument",
                    respuesta["Content-Type"],
                )
                contenido = b"".join(respuesta.streaming_content)
                libro = load_workbook(BytesIO(contenido), read_only=True)
                hoja = libro["IA"]
                self.assertEqual(
                    hoja["A1"].value,
                    "Cálculo Asistencia I° A",
                )
                self.assertEqual(hoja["D4"].value, "Estudiante")

                reporte = ReporteGenerado.objects.get()
                self.assertEqual(reporte.tipo, "planilla")
                self.assertEqual(reporte.estado, "completado")
                self.assertEqual(reporte.cursos_ids, [self.curso_a.pk])
                self.assertTrue(reporte.archivo.name.endswith(".xlsx"))
        finally:
            shutil.rmtree(media_root, ignore_errors=True)

# Create your tests here.
