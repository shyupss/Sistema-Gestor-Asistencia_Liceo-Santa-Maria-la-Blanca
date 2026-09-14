from django.db import migrations, models
import django.db.models.deletion


def vincular_profesores(apps, schema_editor):
    Curso = apps.get_model("academico", "Curso")
    Funcionario = apps.get_model("alertas", "Funcionario")
    funcionarios = {
        funcionario.nombre.strip().casefold(): funcionario
        for funcionario in Funcionario.objects.all()
    }

    for curso in Curso.objects.exclude(profesor_jefe_texto=""):
        texto = curso.profesor_jefe_texto.strip().casefold()
        funcionario = funcionarios.get(texto) or funcionarios.get(f"profe {texto}")
        if funcionario is not None:
            curso.profesor_jefe_id = funcionario.pk
            curso.save(update_fields=["profesor_jefe"])


class Migration(migrations.Migration):

    dependencies = [
        ("academico", "0002_alter_curso_profesor_jefe"),
        ("alertas", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="curso",
            old_name="profesor_jefe",
            new_name="profesor_jefe_texto",
        ),
        migrations.AddField(
            model_name="curso",
            name="profesor_jefe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="alertas.funcionario",
            ),
        ),
        migrations.RunPython(vincular_profesores, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="curso",
            name="profesor_jefe_texto",
        ),
    ]