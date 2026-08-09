from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reports/", views.reports, name="reports"),
    path("api/machines/", views.machines_json, name="machines_json"),
    path("api/products/", views.products_json, name="products_json"),
]
