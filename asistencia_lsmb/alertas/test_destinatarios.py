"""Destinatarios del correo de alertas: funcionarios_con_permiso y estados_que_notifica_el_rol.

Roles, permisos y estados con nombres arbitrarios.
"""
import importlib
import itertools

from django.db.models import QuerySet
from django.test import TestCase

from alertas.models import (
    Cargo, Cuenta, Estado, EstadoNotificaRol, Funcionario, Permiso, Rol, RolPermiso,
)
from alertas.queries.alcance_queries import tiene_permiso

CODIGO = "revisar_alertas"


def _destinatarios():
    return importlib.import_module("alertas.queries.destinatario_queries")


class DestinatariosBase(TestCase):
    def setUp(self):
        self.permiso = Permiso.objects.get_or_create(codigo=CODIGO, defaults={"nombre": "Revisar"})[0]
        self.otro_permiso = Permiso.objects.create(codigo="otro_permiso_de_prueba", nombre="Otro")
        self.extra = Permiso.objects.create(codigo="permiso_extra_de_prueba", nombre="Extra")
        self.cargo = Cargo.objects.create(nombre="Cargo de prueba")
        self.rol_con = self._rol("Rol con permiso", self.permiso, self.extra)
        self.rol_sin = self._rol("Rol sin permisos")
        self.rol_otro = self._rol("Rol con otro permiso", self.otro_permiso)
        self._numeros = itertools.count(1)

    def _rol(self, nombre, *permisos):
        rol = Rol.objects.create(nombre=nombre)
        for permiso in permisos:
            RolPermiso.objects.create(rol=rol, permiso=permiso)
        return rol

    def _funcionario(self, rol=None, activo=True, cuenta_activa=True):
        numero = next(self._numeros)
        funcionario = Funcionario.objects.create(
            cargo=self.cargo, rut=f"{numero:08d}-9", nombre=f"Funcionario {numero}",
            email=f"funcionario{numero}@liceo.cl", activo=activo,
        )
        if rol is not None:
            Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=cuenta_activa)
        return funcionario


class FuncionariosConPermisoTests(DestinatariosBase):
    def setUp(self):
        super().setUp()
        self.entra = self._funcionario(self.rol_con)
        self.inactivo = self._funcionario(self.rol_con, activo=False)
        self.cuenta_inactiva = self._funcionario(self.rol_con, cuenta_activa=False)
        self.rol_sin_permiso = self._funcionario(self.rol_sin)
        self.otro_permiso = self._funcionario(self.rol_otro)
        self.sin_cuenta = self._funcionario()
        self.entra_tambien = self._funcionario(self.rol_con)

    def _con_permiso(self, codigo=CODIGO):
        return _destinatarios().funcionarios_con_permiso(codigo)

    def test_entra_solo_el_activo_con_cuenta_activa_y_permiso(self):
        self.assertEqual(list(self._con_permiso()), [self.entra, self.entra_tambien])

    def test_no_entran_inactivos_cuentas_inactivas_ni_roles_sin_el_permiso(self):
        resultado = set(self._con_permiso())
        for nombre in ("inactivo", "cuenta_inactiva", "rol_sin_permiso", "otro_permiso", "sin_cuenta"):
            with self.subTest(caso=nombre):
                self.assertNotIn(getattr(self, nombre), resultado)

    def test_sin_duplicados_aunque_el_rol_tenga_varios_permisos(self):
        resultado = list(self._con_permiso())
        self.assertEqual(len(resultado), len(set(resultado)))
        self.assertEqual(list(self._con_permiso("permiso_extra_de_prueba")), [self.entra, self.entra_tambien])

    def test_ordenado_por_id(self):
        resultado = list(self._con_permiso())
        self.assertEqual(resultado, sorted(resultado, key=lambda funcionario: funcionario.pk))

    def test_coincide_con_tiene_permiso(self):
        for codigo in (CODIGO, "otro_permiso_de_prueba", "permiso_extra_de_prueba", "no_existe"):
            with self.subTest(codigo=codigo):
                esperado = {f for f in Funcionario.objects.all() if tiene_permiso(f, codigo)}
                self.assertEqual(set(self._con_permiso(codigo)), esperado)

    def test_trae_cuenta_y_rol_sin_consultar_por_fila(self):
        with self.assertNumQueries(1):
            nombres = [f.cuenta.rol.nombre for f in self._con_permiso()]
        self.assertEqual(nombres, ["Rol con permiso", "Rol con permiso"])

    def test_devuelve_un_queryset_de_funcionarios(self):
        resultado = self._con_permiso()
        self.assertIsInstance(resultado, QuerySet)
        self.assertEqual(resultado.model, Funcionario)


class EstadosQueNotificaElRolTests(DestinatariosBase):
    def setUp(self):
        super().setUp()
        self.uno = Estado.objects.create(nombre="Uno", umbral_minimo=70, es_no_ideal=True)
        self.dos = Estado.objects.create(nombre="Dos", umbral_minimo=0, es_no_ideal=True)
        self.tres = Estado.objects.create(nombre="Tres", umbral_minimo=40, es_no_ideal=True)
        EstadoNotificaRol.objects.create(rol=self.rol_con, estado=self.tres)
        EstadoNotificaRol.objects.create(rol=self.rol_con, estado=self.uno)
        EstadoNotificaRol.objects.create(rol=self.rol_otro, estado=self.dos)

    def test_devuelve_los_ids_de_los_estados_del_rol(self):
        self.assertEqual(
            sorted(_destinatarios().estados_que_notifica_el_rol(self.rol_con)),
            sorted([self.uno.pk, self.tres.pk]),
        )

    def test_acepta_el_id_del_rol(self):
        self.assertEqual(list(_destinatarios().estados_que_notifica_el_rol(self.rol_otro.pk)), [self.dos.pk])

    def test_sin_filas_devuelve_vacio(self):
        self.assertEqual(list(_destinatarios().estados_que_notifica_el_rol(self.rol_sin)), [])
