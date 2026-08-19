from django.urls import path

from . import views

urlpatterns = [
    path("", views.plan_list, name="plan_list"),
    path("new/", views.plan_create, name="plan_create"),
    path("<int:pk>/", views.plan_detail, name="plan_detail"),
    path("<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("<int:pk>/items/save/", views.item_save, name="plan_item_save"),
    path("<int:pk>/operate/", views.plan_operate, name="plan_operate"),
    path("<int:pk>/status/", views.plan_set_status, name="plan_set_status"),
    path("mold-change-dates/", views.mold_change_dates, name="mold_change_dates"),
    path("weekday/", views.weekday_for_date, name="weekday_for_date"),
    path("product-insights/", views.product_insights, name="product_insights"),
    path("calendar/", views.plan_calendar_json, name="plan_calendar_json"),
]
