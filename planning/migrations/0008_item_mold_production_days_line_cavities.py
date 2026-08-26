import json

from django.db import migrations, models
import django.db.models.deletion


def forwards_copy(apps, schema_editor):
    WeeklyPlanItem = apps.get_model("planning", "WeeklyPlanItem")
    WeeklyPlanLine = apps.get_model("planning", "WeeklyPlanLine")
    for item in WeeklyPlanItem.objects.all():
        lines = list(WeeklyPlanLine.objects.filter(item_id=item.pk).order_by("id"))
        if not lines:
            continue
        first = lines[0]
        if first.mold_id and not item.mold_id:
            item.mold_id = first.mold_id
            item.save(update_fields=["mold_id"])
        cav = item.active_cavities or 1
        for line in lines:
            WeeklyPlanLine.objects.filter(pk=line.pk).update(
                active_cavities=cav,
                mold_id=item.mold_id or line.mold_id,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0009_plan_date_unique_and_excel_upload"),
        ("planning", "0007_plan_date_unique_and_excel_upload"),
    ]

    operations = [
        migrations.AddField(
            model_name="weeklyplanitem",
            name="mold",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="catalog.moldoption",
                verbose_name="نوع قالب",
            ),
        ),
        migrations.AddField(
            model_name="weeklyplanitem",
            name="production_days",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="فهرست {date, shift, note}",
                verbose_name="روزهای تولید",
            ),
        ),
        migrations.AddField(
            model_name="weeklyplanline",
            name="active_cavities",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="تعداد حفره"),
        ),
        migrations.RunPython(forwards_copy, noop_reverse),
    ]
