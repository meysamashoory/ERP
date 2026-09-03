# Generated manually for obsolete transfer level cleanup

from django.db import migrations

OBSOLETE_PRODUCT_LEVELS = {
    "product_info",
    "product_bom",
    "product_consumables",
    "info",
    "packaging",
}


def deactivate_obsolete(apps, schema_editor):
    SystemNamingKey = apps.get_model("catalog", "SystemNamingKey")
    for row in SystemNamingKey.objects.filter(key__startswith="transfer.").iterator():
        parts = row.key.split(".")
        if len(parts) >= 4 and parts[1] in ("level", "field") and parts[2] == "product_data":
            if parts[3] in OBSOLETE_PRODUCT_LEVELS and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active"])
    SystemNamingKey.objects.filter(
        key__startswith="transfer.dest.inventory_orders", is_active=True
    ).update(is_active=False)
    SystemNamingKey.objects.filter(
        key__startswith="transfer.level.inventory_orders.", is_active=True
    ).update(is_active=False)
    SystemNamingKey.objects.filter(
        key__startswith="transfer.field.inventory_orders.", is_active=True
    ).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0017_flexible_dataset_and_naming_is_key"),
    ]

    operations = [
        migrations.RunPython(deactivate_obsolete, noop_reverse),
    ]
