from django.urls import path

from . import views

urlpatterns = [
    path("", views.production_list, name="production_list"),
    path("programs/", views.program_list, name="program_list"),
    path("history/", views.production_history, name="production_history"),
    path("history/conflicts/", views.production_conflicts, name="production_conflicts"),
    path("history/<int:pk>/", views.production_history_detail, name="production_history_detail"),
    path(
        "history/archive/<int:pk>/",
        views.production_history_archive_detail,
        name="production_history_archive_detail",
    ),
    path("programs/<int:pk>/status/", views.program_status, name="program_status"),
    path("programs/<int:program_pk>/entry/", views.entry_create, name="entry_create"),
    path("entries/<int:pk>/edit/", views.entry_edit, name="entry_edit"),
    path("pipes/new/", views.pipe_create, name="pipe_create"),
    path("pipes/<int:pk>/edit/", views.pipe_edit, name="pipe_edit"),
]
