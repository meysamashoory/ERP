import jdatetime
from django.test import TestCase

from .utils import mold_change_date_candidates, start_of_week
from .models import persian_weekday, Weekday


class MoldChangeDateLogicTests(TestCase):
    def test_start_of_week_is_saturday(self):
        # 1403-05-15 is a Monday; its week starts on Saturday 1403-05-13.
        d = jdatetime.date(1403, 5, 15)
        self.assertEqual(d.weekday(), 2)  # Doshanbe
        start = start_of_week(d)
        self.assertEqual(start.weekday(), 0)  # Shanbe
        self.assertEqual(start, jdatetime.date(1403, 5, 13))

    def test_two_occurrences_when_weekday_after_planning_day(self):
        # Planning on Monday (Doshanbe); mold change on Wednesday (Chaharshanbe)
        # yields both this week's and next week's Wednesday.
        plan_date = jdatetime.date(1403, 5, 15)  # Doshanbe
        dates = mold_change_date_candidates(plan_date, Weekday.CHAHARSHANBE)
        self.assertEqual(len(dates), 2)
        self.assertTrue(all(d.weekday() == 4 for d in dates))
        self.assertTrue(all(d >= plan_date for d in dates))

    def test_single_occurrence_when_weekday_already_passed(self):
        # Planning on Sunday (Yekshanbe); Saturday already passed this week,
        # so only next week's Saturday remains.
        plan_date = jdatetime.date(1403, 5, 14)  # Yekshanbe
        self.assertEqual(plan_date.weekday(), 1)
        dates = mold_change_date_candidates(plan_date, Weekday.SHANBE)
        self.assertEqual(len(dates), 1)
        self.assertEqual(dates[0].weekday(), 0)

    def test_candidates_for_different_weekdays_are_disjoint(self):
        plan_date = jdatetime.date(1403, 5, 15)
        mon = {d.strftime("%Y-%m-%d") for d in mold_change_date_candidates(plan_date, Weekday.DOSHANBE)}
        wed = {d.strftime("%Y-%m-%d") for d in mold_change_date_candidates(plan_date, Weekday.CHAHARSHANBE)}
        self.assertTrue(mon)
        self.assertTrue(wed)
        self.assertFalse(mon & wed)

    def test_persian_weekday_name(self):
        self.assertEqual(persian_weekday(jdatetime.date(1403, 5, 13)), "شنبه")


class EmptyZeroWidgetTests(TestCase):
    def test_line_form_renders_blank_for_zero(self):
        from .forms import WeeklyPlanLineForm
        form = WeeklyPlanLineForm()
        html = str(form["quantity"]) + str(form["cycle"])
        self.assertNotIn('value="0"', html)

class WeeklyPlanDateUniqueTests(TestCase):
    def test_duplicate_plan_date_rejected(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from planning.forms import WeeklyPlanForm
        from planning.models import WeeklyPlan

        call_command("seed_demo")
        existing = WeeklyPlan.objects.first()
        form = WeeklyPlanForm(data={
            "program_number": "BP-UNIQUE-TEST",
            "date": existing.date.strftime("%Y/%m/%d"),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)
