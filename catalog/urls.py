from django.urls import path

from . import views

urlpatterns = [
    path("data/excel/", views.excel_list, name="excel_list"),
    path("data/excel/import/", views.excel_import, name="excel_import"),
    path("data/excel/preview/", views.excel_preview, name="excel_preview"),
    path("data/excel/import/confirm/", views.excel_import_confirm, name="excel_import_confirm"),
    path("data/excel/<int:pk>/", views.excel_detail, name="excel_detail"),
    path("data/excel/tables/<int:pk>/save/", views.excel_table_save, name="excel_table_save"),
    path("data/excel/tables/<int:pk>/delete/", views.excel_table_delete, name="excel_table_delete"),
    path("data/excel/<int:pk>/delete/", views.excel_file_delete, name="excel_file_delete"),
]
