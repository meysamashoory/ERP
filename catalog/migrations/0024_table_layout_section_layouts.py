from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0023_systemnamingkey_default_width_px"),
    ]

    operations = [
        migrations.AddField(
            model_name="tablelayoutsettings",
            name="section_layouts",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    'مثال: {"reports": {"row_height_px": 36, "col_border": true, '
                    '"row_border": true, "width_locked": false}}'
                ),
                verbose_name="تنظیمات نمایش به تفکیک منو",
            ),
        ),
        migrations.AlterField(
            model_name="tablelayoutsettings",
            name="row_height_px",
            field=models.PositiveSmallIntegerField(
                default=36,
                help_text="بین ۵ تا ۱۲۰. برای هر منو جداگانه در section_layouts ذخیره می‌شود.",
                verbose_name="ارتفاع ردیف جداول (پیکسل)",
            ),
        ),
        migrations.AlterField(
            model_name="tablelayoutsettings",
            name="section_width_locks",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='همگام با section_layouts. مثال: {"reports": false, "history": true}',
                verbose_name="قفل عرض ستون به تفکیک بخش",
            ),
        ),
        migrations.AlterModelOptions(
            name="tablelayoutsettings",
            options={
                "verbose_name": "تنظیمات نمایش جداول",
                "verbose_name_plural": "تنظیمات نمایش جداول (ارتفاع ردیف، مرز و قفل عرض)",
            },
        ),
    ]
