from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0022_pipelengthcut_line_speed"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemnamingkey",
            name="default_width_px",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text=(
                    "پیش‌فرض عرض ستون هنگام افزودن به گزارش. "
                    "۰ = استفاده از پیش‌فرض نوع (متن/عدد/تاریخ/…)."
                ),
                verbose_name="عرض ستون (پیکسل)",
            ),
        ),
        migrations.AlterField(
            model_name="tablelayoutsettings",
            name="row_height_px",
            field=models.PositiveSmallIntegerField(
                default=36,
                help_text="بین ۱۸ تا ۱۲۰. روی همه جداول سامانه اعمال می‌شود.",
                verbose_name="ارتفاع یکنواخت ردیف جداول (پیکسل)",
            ),
        ),
    ]
