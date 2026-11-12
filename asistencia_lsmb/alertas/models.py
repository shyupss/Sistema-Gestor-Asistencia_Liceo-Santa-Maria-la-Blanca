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
    genera_alerta = models.BooleanField(default=False)
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


class ConfiguracionAlerta(models.Model):
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE, related_name='configuraciones')
    cargo = models.ForeignKey(Cargo, on_delete=models.CASCADE, related_name='configuraciones_alerta')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['estado', 'cargo'],
                name='uq_config_alerta_estado_cargo',
            )
        ]


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


class ConfigNotificaciones(models.Model):
    """Configuración global de notificaciones: existe una sola fila (id=1)."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    activa = models.BooleanField(default=True)
    frecuencia_dias = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1)]
    )
    # 1 = lunes ... 7 = domingo (isoweekday)
    dia_semana_envio = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    hora_envio = models.TimeField(default=datetime.time(16, 0))

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name='ck_config_notificaciones_singleton'),
            models.CheckConstraint(
                condition=Q(frecuencia_dias__gte=1), name='ck_config_notificaciones_frecuencia',
            ),
            models.CheckConstraint(
                condition=Q(dia_semana_envio__gte=1, dia_semana_envio__lte=7),
                name='ck_config_notificaciones_dia_semana',
            ),
        ]

    @classmethod
    def obtener(cls):
        """Devuelve la única fila de configuración, creándola si no existe."""
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return 'Configuración de notificaciones'


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
