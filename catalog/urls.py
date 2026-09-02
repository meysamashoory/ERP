from django.urls import path

from . import views

urlpatterns = [
    path("data/system/", views.system_data_hub, name="system_data"),
    path("data/system/naming/", views.system_naming_keys, name="system_naming_keys"),
    path("data/system/naming/save/", views.system_naming_key_save, name="system_naming_key_save"),
    path("data/system/naming/delete/", views.system_naming_key_delete, name="system_naming_key_delete"),
    path("data/system/columns/", views.system_table_columns, name="system_table_columns"),
    path("data/system/admin-header/", views.system_admin_header_save, name="system_admin_header_save"),
    path("data/system/<slug:key>/", views.system_section, name="system_section"),
    path("data/products/", views.product_data_hub, name="product_data"),
    path("data/products/save/", views.product_data_save, name="product_data_save"),
    path("data/products/delete/", views.product_data_delete, name="product_data_delete"),
    path("data/excel/", views.excel_list, name="excel_list"),
    path("data/excel/import/", views.excel_import, name="excel_import"),
    path("data/excel/preview/", views.excel_preview, name="excel_preview"),
    path("data/excel/import/confirm/", views.excel_import_confirm, name="excel_import_confirm"),
    path("data/excel/<int:pk>/", views.excel_detail, name="excel_detail"),
    path("data/excel/tables/<int:pk>/save/", views.excel_table_save, name="excel_table_save"),
    path("data/excel/tables/<int:pk>/transfer/", views.excel_table_transfer, name="excel_table_transfer"),
    path("data/excel/tables/<int:pk>/delete/", views.excel_table_delete, name="excel_table_delete"),
    path("data/excel/<int:pk>/delete/", views.excel_file_delete, name="excel_file_delete"),
]
