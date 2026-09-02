import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0008_item_mold_production_days_line_cavities"),
    ]

    operations = [
        migrations.AlterField(
            model_name="weeklyplanline",
            name="production_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="catalog.productiontypeoption",
                verbose_name="نوع تولید",
            ),
        ),
    ]
