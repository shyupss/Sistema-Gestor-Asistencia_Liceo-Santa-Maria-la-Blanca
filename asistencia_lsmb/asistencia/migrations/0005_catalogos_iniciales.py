from django.db import migrations

# nombre -> cuenta_como_ausencia
TIPOS_ASISTENCIA = {
    'presente': False,
    'ausente': True,
    'atrasado': True,
    'justificado': False,
}
# nombre -> (es_estado_final, cubre_ausencia, descripcion)
ESTADOS_SOLICITUD = {
    'pendiente': (False, False, 'Solicitud pendiente de revisión.'),
    'aceptada': (True, True, 'Solicitud aceptada; cubre la ausencia.'),
    'rechazada': (True, False, 'Solicitud rechazada; no cubre la ausencia.'),
}


def sembrar_catalogos(apps, schema_editor):
    """Idempotente. Crea lo que falte, buscando por nombre sin distinguir mayúsculas.

    No modifica valores de filas existentes; solo renombra "aprobada" a "aceptada"
    cuando "aceptada" no existe (nombre usado en una carga anterior).
    """
    Tipos_Asistencia = apps.get_model('asistencia', 'Tipos_Asistencia')
    Estados_Solicitud = apps.get_model('asistencia', 'Estados_Solicitud')

    anterior = Estados_Solicitud.objects.filter(nombre__iexact='aprobada').first()
    if anterior and not Estados_Solicitud.objects.filter(nombre__iexact='aceptada').exists():
        anterior.nombre = 'aceptada'
        if anterior.descripcion == 'Solicitud aprobada; cubre la ausencia.':
            anterior.descripcion = 'Solicitud aceptada; cubre la ausencia.'
        anterior.save(update_fields=['nombre', 'descripcion'])

    for nombre, ausencia in TIPOS_ASISTENCIA.items():
        Tipos_Asistencia.objects.get_or_create(
            nombre__iexact=nombre,
            defaults={'nombre': nombre, 'cuenta_como_ausencia': ausencia},
        )
    for nombre, (final, cubre, descripcion) in ESTADOS_SOLICITUD.items():
        Estados_Solicitud.objects.get_or_create(
            nombre__iexact=nombre,
            defaults={
                'nombre': nombre,
                'es_estado_final': final,
                'cubre_ausencia': cubre,
                'descripcion': descripcion,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('asistencia', '0004_paso_lista_sin_jornada'),
    ]

    operations = [
        migrations.RunPython(sembrar_catalogos, migrations.RunPython.noop),
    ]
