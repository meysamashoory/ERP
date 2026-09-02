# Generated manually — seed PDF planning process stages

from django.db import migrations


def seed_processes(apps, schema_editor):
    from planning.process_data import ensure_default_processes

    ensure_default_processes(force=True)


def unseed(apps, schema_editor):
    PlanningProcessDefinition = apps.get_model("planning", "PlanningProcessDefinition")
    PlanningProcessDefinition.objects.filter(code__in=["mto", "mts"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0011_planning_process_stages"),
    ]

    operations = [
        migrations.RunPython(seed_processes, unseed),
    ]
