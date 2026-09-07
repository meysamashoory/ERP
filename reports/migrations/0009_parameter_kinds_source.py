from django.db import migrations, models


def remap_parameter_kinds(apps, schema_editor):
    ReportParameterDef = apps.get_model("reports", "ReportParameterDef")
    ReportParameterDef.objects.filter(kind="date").update(kind="day_date")
    ReportParameterDef.objects.filter(kind="code").update(kind="product_code")
    ReportParameterDef.objects.filter(kind="number").update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0008_report_conditions_and_parameters"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportparameterdef",
            name="source_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="خالی = همه منابع. در غیر این صورت پارامتر فقط در منبع انتخاب‌شده معنا دارد.",
                max_length=80,
                verbose_name="فیلد منابع",
            ),
        ),
        migrations.AlterField(
            model_name="reportparameterdef",
            name="kind",
            field=models.CharField(
                choices=[
                    ("day_date", "تاریخ روز"),
                    ("year", "سال"),
                    ("product_code", "کد کالا"),
                    ("unique_code", "کد یکتا"),
                    ("mold_number", "شماره قالب"),
                    ("voucher_number", "شماره حواله"),
                ],
                default="day_date",
                max_length=20,
                verbose_name="نوع",
            ),
        ),
        migrations.AlterField(
            model_name="reportparameterdef",
            name="sample_value",
            field=models.CharField(
                blank=True,
                default="",
                help_text="مقدار اولیه هنگام ساخت پارامتر؛ پس از اعمال در گزارش نیز به‌روز می‌شود.",
                max_length=120,
                verbose_name="مقدار پیش‌فرض",
            ),
        ),
        migrations.RunPython(remap_parameter_kinds, migrations.RunPython.noop),
    ]
