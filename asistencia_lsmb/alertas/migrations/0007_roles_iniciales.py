from django.db import migrations

# nombre, alcance, recibe_todos_los_cursos_marcados
ROLES = [
    ('Asistente social', 'todos', True),
    ('Rector', 'todos', False),
    ('Inspector general', 'todos', False),
    ('Inspector', 'seleccionados', False),
]


def crear_roles_iniciales(apps, schema_editor):
    """Idempotente. Crea los roles que falten y les asigna 'revisar_alertas'.

    Un rol que ya existe no se toca (ni sus campos ni sus permisos): su alcance
    puede haberse editado en el admin.
    """
    Rol = apps.get_model('alertas', 'Rol')
    Permiso = apps.get_model('alertas', 'Permiso')
    RolPermiso = apps.get_model('alertas', 'RolPermiso')

    permiso, _ = Permiso.objects.get_or_create(
        codigo='revisar_alertas',
        defaults={
            'nombre': 'Revisar alertas',
            'descripcion': 'Permite revisar alertas y recibir notificaciones de alertas.',
        },
    )
    for nombre, alcance, recibe_todos in ROLES:
        rol, creado = Rol.objects.get_or_create(
            nombre__iexact=nombre,
            defaults={
                'nombre': nombre,
                'alcance': alcance,
                'recibe_todos_los_cursos_marcados': recibe_todos,
            },
        )
        if creado:
            RolPermiso.objects.get_or_create(rol=rol, permiso=permiso)


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0006_datos_iniciales_roles_notificaciones'),
    ]

    operations = [
        migrations.RunPython(crear_roles_iniciales, migrations.RunPython.noop),
    ]
