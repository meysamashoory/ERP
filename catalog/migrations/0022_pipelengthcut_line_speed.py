from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0021_pipe_calc_depot_matrix_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelengthcut",
            name="line_speed_m_per_min",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("0"),
                help_text="اگر صفر باشد از سرعت پروفایل سایز استفاده می‌شود.",
                max_digits=10,
                verbose_name="سرعت تولید خط (m/min)",
            ),
        ),
    ]
