from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .feriados import FeriadosError, obtener_feriados, validar_dia_asistencia


class FeriadosServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("asistencia.services.feriados.urlopen")
    def test_obtiene_y_cachea_feriados_del_año(self, urlopen):
        respuesta = urlopen.return_value.__enter__.return_value
        respuesta.__iter__.return_value = iter([])
        respuesta.read.return_value = b'[{"date": "2026-09-18"}]'

        with patch("asistencia.services.feriados.json.load", return_value=[
            {"date": "2026-09-18"},
        ]):
            self.assertEqual(obtener_feriados(2026), {"2026-09-18"})
            self.assertEqual(obtener_feriados(2026), {"2026-09-18"})

        urlopen.assert_called_once()

    @patch("asistencia.services.feriados.obtener_feriados", return_value={"2026-09-18"})
    def test_rechaza_un_feriado(self, _obtener_feriados):
        with self.assertRaises(FeriadosError):
            validar_dia_asistencia(date(2026, 9, 18))
