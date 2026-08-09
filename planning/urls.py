from django.urls import path

from . import views

urlpatterns = [
    path("", views.plan_list, name="plan_list"),
    path("new/", views.plan_create, name="plan_create"),
    path("<int:pk>/", views.plan_detail, name="plan_detail"),
    path("<int:pk>/items/save/", views.item_save, name="plan_item_save"),
    path("<int:pk>/status/", views.plan_set_status, name="plan_set_status"),
    path("mold-change-dates/", views.mold_change_dates, name="mold_change_dates"),
]
