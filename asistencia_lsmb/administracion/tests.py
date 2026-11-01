from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .services.carga_archivos import validar_archivo_carga


class ValidarArchivoCargaTests(TestCase):
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
