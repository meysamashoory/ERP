from django.urls import path

from . import views

urlpatterns = [
    # Reports
    path("reports/", views.report_list, name="report_list"),
    path("reports/create/", views.report_create, name="report_create"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("reports/<int:pk>/edit/", views.report_edit, name="report_edit"),
    path("reports/<int:pk>/delete/", views.report_delete, name="report_delete"),
    path("reports/<int:pk>/send/", views.report_send, name="report_send"),
    path("reports/<int:pk>/copy/", views.report_copy, name="report_copy"),
    # Print forms
    path("forms/", views.form_list, name="print_form_list"),
    path("forms/create/", views.form_create, name="print_form_create"),
    path("forms/<int:pk>/", views.form_detail, name="print_form_detail"),
    path("forms/<int:pk>/edit/", views.form_edit, name="print_form_edit"),
    path("forms/<int:pk>/delete/", views.form_delete, name="print_form_delete"),
    path("forms/<int:pk>/send/", views.form_send, name="print_form_send"),
    path("forms/<int:pk>/copy/", views.form_copy, name="print_form_copy"),
]
