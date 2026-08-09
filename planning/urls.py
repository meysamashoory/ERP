from django.urls import path

from . import views

urlpatterns = [
    path("", views.plan_list, name="plan_list"),
    path("new/", views.plan_create, name="plan_create"),
    path("<int:pk>/", views.plan_detail, name="plan_detail"),
    path("<int:pk>/items/add/", views.item_add, name="plan_item_add"),
    path("<int:pk>/submit/", views.plan_submit, name="plan_submit"),
    path("<int:pk>/approve/", views.plan_approve, name="plan_approve"),
    path("mold-change-dates/", views.mold_change_dates, name="mold_change_dates"),
]
