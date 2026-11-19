import datetime

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class Cargo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre


class Funcionario(models.Model):
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='funcionarios')
    rut = models.CharField(max_length=15, unique=True)
    nombre = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # El correo identifica al usuario que entra con Google: único sin distinguir mayúsculas.
            models.UniqueConstraint(Lower('email'), name='uq_funcionario_email_ci'),
            models.CheckConstraint(condition=~Q(email=''), name='ck_funcionario_email_no_vacio'),
        ]

    def __str__(self):
        return f"{self.nombre} - {self.rut}"


class Estado(models.Model):
    nombre = models.CharField(max_length=20, unique=True)
    umbral_minimo = models.DecimalField(max_digits=5, decimal_places=2)
    es_no_ideal = models.BooleanField(default=False)
    # Nombre de la familia de color de la paleta de Tailwind (tailwind.config.js)
    COLORES = [
        ("gris", "Gris"),
        ("verde", "Verde"),
        ("amarillo", "Amarillo"),
        ("rojo", "Rojo"),
        ("azul", "Azul"),
        ("violeta", "Violeta"),
        ("naranja", "Naranja"),
        ("turquesa", "Turquesa"),
        ("rosa", "Rosa"),
    ]
    color = models.CharField(max_length=20, default="gris", choices=COLORES)

    def __str__(self):
        return self.nombre


class Alerta(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='alertas')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='alertas'
    )
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='alertas')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)  # null = vigente
    MOTIVOS_CIERRE = [
        ('recuperado', 'Recuperado'),
        ('cambio_estado', 'Cambio de estado'),
        ('fin_matricula', 'Fin de matrícula'),
        ('fin_periodo', 'Fin de período'),
    ]
    motivo_cierre = models.CharField(max_length=20, null=True, blank=True, choices=MOTIVOS_CIERRE)
    revisada = models.BooleanField(default=False)
    funcionario_revisa = models.ForeignKey(
        Funcionario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='alertas_revisadas',
    )
    fecha_revision = models.DateTimeField(null=True, blank=True)
    nota = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'periodo'],
                condition=Q(fecha_cierre__isnull=True),
                name='uq_alerta_vigente_alumno_periodo',
            )
        ]


class EstadoAlumno(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='estados')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='estados_alumno'
    )
    estado = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='estados_alumno')
    porcentaje_asistencia = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'periodo'],
                name='uq_estado_alumno_periodo',
            )
        ]


class HistorialEstadoAlumno(models.Model):
    alumno = models.ForeignKey('academico.Alumno', on_delete=models.CASCADE, related_name='historial_estados')
    periodo = models.ForeignKey(
        'academico.PeriodoAcademico', on_delete=models.CASCADE, related_name='historial_estados_alumno'
    )
    estado_nuevo = models.ForeignKey(Estado, on_delete=models.PROTECT, related_name='cambios_nuevos')
    estado_anterior = models.ForeignKey(
        Estado,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cambios_anteriores',
    )
    fecha_cambio = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------
# Roles, permisos, cuentas y notificaciones
# ---------------------------------------------------------------------

class Rol(models.Model):
    ALCANCE_TODOS = 'todos'
    ALCANCE_SELECCIONADOS = 'seleccionados'
    ALCANCES = [
        (ALCANCE_TODOS, 'Todos los cursos'),
        (ALCANCE_SELECCIONADOS, 'Cursos seleccionados'),
    ]

    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    # True: recibe las notificaciones de todos los cursos marcados (asistente social).
    recibe_todos_los_cursos_marcados = models.BooleanField(default=False)
    alcance = models.CharField(max_length=20, choices=ALCANCES, default=ALCANCE_SELECCIONADOS)

    def __str__(self):
        return self.nombre


class Permiso(models.Model):
    codigo = models.CharField(max_length=50, unique=True)  # debe existir 'revisar_alertas'
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.codigo


class RolPermiso(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='permisos_asignados')
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, related_name='roles_asignados')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['rol', 'permiso'], name='uq_rol_permiso'),
        ]


class FuncionarioCurso(models.Model):
    """Cursos a los que accede un funcionario cuyo rol tiene alcance 'seleccionados'."""
    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.CASCADE, related_name='cursos_asignados'
    )
    curso = models.ForeignKey(
        'academico.Curso', on_delete=models.CASCADE, related_name='funcionarios_asignados'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['funcionario', 'curso'], name='uq_funcionario_curso'),
        ]


class EstadoNotificaRol(models.Model):
    """Roles adicionales que se notifican según el estado del alumno."""
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name='roles_notificados')
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name='estados_notificados')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['estado', 'rol'], name='uq_estado_notifica_rol'),
        ]


class Notificacion(models.Model):
    """Un registro por destinatario por ejecución del job de notificaciones."""
    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.PROTECT, related_name='notificaciones'
    )
    canal = models.CharField(max_length=20, default='email')
    fecha_envio = models.DateTimeField()


class NotificacionCurso(models.Model):
    """Cursos que incluyó cada notificación."""
    notificacion = models.ForeignKey(
        Notificacion, on_delete=models.CASCADE, related_name='cursos'
    )
    curso = models.ForeignKey(
        'academico.Curso', on_delete=models.CASCADE, related_name='notificaciones_curso'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['notificacion', 'curso'], name='uq_notificacion_curso',
            ),
        ]


class ConfigGeneral(models.Model):
    """Configuración global del sistema: existe una sola fila (id=1).

    Cuándo se envían las notificaciones, según `modo` (siempre a `hora_envio`).
    Aquí solo se documenta; el envío todavía no está implementado:
    - diario: cada día hábil. Si el día no es hábil, se salta (no se pospone).
    - semanal: el día de la semana `dia_semana_envio`. Si no es hábil, pasa al
      siguiente día hábil.
    - mensual: el día del mes `dia_mes_envio` (1 a 31). Si el mes no tiene ese
      día, se usa el último día del mes; y si ese día no es hábil, pasa al
      siguiente día hábil.
    """
    MODO_DIARIO = 'diario'
    MODO_SEMANAL = 'semanal'
    MODO_MENSUAL = 'mensual'
    MODOS = [
        (MODO_DIARIO, 'Diario'),
        (MODO_SEMANAL, 'Semanal'),
        (MODO_MENSUAL, 'Mensual'),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    activa = models.BooleanField(default=True)
    modo = models.CharField(max_length=10, choices=MODOS, default=MODO_SEMANAL)
    # Solo para modo semanal. 1 = lunes ... 7 = domingo (isoweekday)
    dia_semana_envio = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    # Solo para modo mensual.
    dia_mes_envio = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    hora_envio = models.TimeField(default=datetime.time(16, 0))
    # Meta de asistencia (%). Entera a propósito: los servicios la devuelven en
    # dicts que se serializan a JSON y Decimal rompería json.dumps.
    meta_asistencia = models.PositiveSmallIntegerField(
        default=75, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        verbose_name = 'Configuración general'
        verbose_name_plural = 'Configuración general'
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name='ck_config_general_singleton'),
            # Los valores deben coincidir con MODOS (Meta no ve los atributos de la clase).
            models.CheckConstraint(
                condition=Q(modo__in=['diario', 'semanal', 'mensual']),
                name='ck_config_general_modo',
            ),
            models.CheckConstraint(
                condition=Q(dia_semana_envio__gte=1, dia_semana_envio__lte=7),
                name='ck_config_general_dia_semana',
            ),
            models.CheckConstraint(
                condition=Q(dia_mes_envio__gte=1, dia_mes_envio__lte=31),
                name='ck_config_general_dia_mes',
            ),
            models.CheckConstraint(
                condition=Q(meta_asistencia__gte=0, meta_asistencia__lte=100),
                name='ck_config_general_meta',
            ),
        ]

    @classmethod
    def obtener(cls):
        """Devuelve la única fila de configuración, creándola si no existe."""
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return 'Configuración general'


class Cuenta(models.Model):
    """Acceso de un funcionario al sistema. El correo vive solo en Funcionario.email.

    El vínculo con el usuario de Django (Google OAuth) se agregará después.
    """
    funcionario = models.OneToOneField(
        Funcionario, on_delete=models.PROTECT, related_name='cuenta'
    )
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='cuentas')
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.funcionario.email} ({self.rol})"
