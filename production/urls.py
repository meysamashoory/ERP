from django.urls import path

from . import views

urlpatterns = [
    path("", views.production_list, name="production_list"),
    path("fittings/new/", views.fitting_create, name="fitting_create"),
    path("pipes/new/", views.pipe_create, name="pipe_create"),
]
