from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0005_printform_purpose_linked_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedreport",
            name="access_mode",
            field=models.CharField(
                choices=[
                    ("readonly", "گزارش فقط خواندنی"),
                    ("editable", "گزارش قابل ویرایش"),
                ],
                default="readonly",
                max_length=20,
                verbose_name="نوع دسترسی",
            ),
        ),
        migrations.AddField(
            model_name="savedreport",
            name="entry_data",
            field=models.JSONField(blank=True, default=dict, verbose_name="داده ثبت‌شده"),
        ),
        migrations.AlterField(
            model_name="savedreport",
            name="data_source",
            field=models.CharField(
                choices=[
                    ("fitting", "تولید اتصالات"),
                    ("pipe", "تولید لوله"),
                    ("product", "اطلاعات کالا و موجودی"),
                    ("data_entry", "ثبت داده"),
                ],
                default="fitting",
                max_length=20,
                verbose_name="منبع داده",
            ),
        ),
    ]
