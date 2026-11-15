from io import BytesIO
from datetime import date
from unittest.mock import patch

from openpyxl import Workbook
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Cargo, Funcionario
from asistencia.models import Asistencia_Alumnos, Tipos_Asistencia

from .services.carga_archivos import cargar_asistencia, validar_archivo_carga


class ValidarArchivoCargaTests(TestCase):
    def test_lee_libro_mensual_por_hojas_y_resuelve_presentes(self):
        workbook = Workbook()
        primera_hoja = workbook.active
        primera_hoja.title = " 1°A"
        primera_hoja["B1"] = "Curso 1°A"
        primera_hoja.append([])
        primera_hoja.append([])
        primera_hoja.append(["N°", "Nombre Alumno", "Estado", 3, 4, 5, None, None, None, None, "Dias Presente", "%"])
        primera_hoja.append([1, "Ana Pérez (22/04)", "", "x", None, "X", None, None, None, None, 0, 0])
        primera_hoja.append([2, "Alumno Retirado", "Retirado", None, None, None, None, None, None, None, "", ""])

        segunda_hoja = workbook.create_sheet("2A")
        segunda_hoja["B1"] = "Curso 2A"
        segunda_hoja.append([])
        segunda_hoja.append([])
        segunda_hoja.append(["N°", "Nombre Alumno", "Estado", 3, 4, 5, None, None, None, None, "Dias Presente", "%"])
        segunda_hoja.append([1, "Bruno Díaz", "", None, "x", None, None, None, None, None, 0, 0])

        plantilla = workbook.create_sheet("Master ")
        plantilla["B1"] = "Plantilla"

        archivo_buffer = BytesIO()
        workbook.save(archivo_buffer)
        archivo = SimpleUploadedFile(
            "ASISTENCIA AGOSTO 2026.xlsx",
            archivo_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        resultado = validar_archivo_carga(archivo, "Asistencia")

        self.assertEqual(resultado["errores"], [])
        self.assertEqual(resultado["hojas_procesadas"], ["1°A", "2A"])
        self.assertEqual(resultado["dias_registrados"], 3)
        self.assertEqual(len(resultado["registros"]), 6)
        self.assertEqual(
            [(registro["nombre"], registro["fecha"], registro["estado"]) for registro in resultado["registros"]],
            [
                ("Ana Pérez (22/04)", "2026-08-03", "A"),
                ("Ana Pérez (22/04)", "2026-08-04", "P"),
                ("Ana Pérez (22/04)", "2026-08-05", "A"),
                ("Bruno Díaz", "2026-08-03", "P"),
                ("Bruno Díaz", "2026-08-04", "A"),
                ("Bruno Díaz", "2026-08-05", "P"),
            ],
        )

    @patch("asistencia.services.feriados.obtener_feriados", return_value=set())
    def test_carga_asistencia_resuelve_nombre_sin_rut(self, _obtener_feriados):
        periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 31),
        )
        curso = Curso.objects.create(periodo=periodo, nivel=1, grupo="A")
        estado_matricula = EstadoMatricula.objects.create(nombre="vigente")
        alumno = Alumno.objects.create(nombre="Ana Pérez", rut="12.345.678-9")
        Matricula.objects.create(
            alumno=alumno,
            curso=curso,
            periodo=periodo,
            estado_matricula=estado_matricula,
            fecha_matricula=date(2026, 3, 1),
        )
        cargo = Cargo.objects.create(nombre="Administrador")
        Funcionario.objects.create(
            cargo=cargo,
            rut="99.999.999-9",
            nombre="Administrador de prueba",
            email="admin@example.com",
        )
        Tipos_Asistencia.objects.create(nombre="Presente", cuenta_como_ausencia=False)
        Tipos_Asistencia.objects.create(nombre="Ausente", cuenta_como_ausencia=True)

        resultado = cargar_asistencia([
            {
                "rut": "",
                "nombre": "Ana Pérez (22/04)",
                "fecha": "2026-08-03",
                "estado": "A",
                "fila": 5,
            },
            {
                "rut": "",
                "nombre": "Ana Pérez (22/04)",
                "fecha": "2026-08-04",
                "estado": "P",
                "fila": 5,
            },
        ])

        self.assertEqual(resultado["asistencias_creadas"], 2)
        self.assertEqual(Asistencia_Alumnos.objects.count(), 2)

    def test_interpreta_missclick_retiro_y_asistencia_completa(self):
        workbook = Workbook()
        hoja = workbook.active
        hoja.title = "1A"
        hoja["B1"] = "Curso 1°A"
        hoja.append([])
        hoja.append([])
        hoja.append(["N°", "Nombre Alumno", "Estado", 1, 2, 3])
        hoja.append([1, "Alumno Uno", "", "c", "<", "ret"])

        completa = workbook.create_sheet("2A")
        completa["B1"] = "Curso 2°A"
        completa.append([])
        completa.append([])
        completa.append(["N°", "Nombre Alumno", "Estado", 1, 2])
        for numero, marca in enumerate("ASISTENCIACOMPLETA", start=1):
            completa.append([numero, f"Alumno {numero}", "", marca, None])

        archivo_buffer = BytesIO()
        workbook.save(archivo_buffer)
        archivo = SimpleUploadedFile(
            "ASISTENCIA AGOSTO 2026.xlsx",
            archivo_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        resultado = validar_archivo_carga(archivo, "Asistencia")

        self.assertEqual(resultado["errores"], [])
        alumno_uno = [registro for registro in resultado["registros"] if registro["nombre"] == "Alumno Uno"]
        self.assertEqual([(registro["fecha"], registro["estado"]) for registro in alumno_uno], [
            ("2026-08-01", "A"),
            ("2026-08-02", "A"),
        ])
        completos = [registro for registro in resultado["registros"] if registro["hoja"] == "2A"]
        self.assertEqual(len(completos), 36)
        self.assertTrue(all(registro["estado"] == "P" for registro in completos))

    def test_omite_celdas_vacias_de_asistencia(self):
        archivo = SimpleUploadedFile(
            "asistencia.csv",
            (
                "rut,nombre_completo,2026-09-01,2026-10-01\n"
                "11.111.111-1,Estudiante,,P\n"
            ).encode(),
            content_type="text/csv",
        )

        resultado = validar_archivo_carga(archivo, "Asistencia")

        self.assertEqual(resultado["errores"], [])
        self.assertEqual(
            resultado["registros"],
            [{
                "rut": "11111111-1",
                "fecha": "2026-10-01",
                "estado": "P",
                "fila": 2,
            }],
        )
