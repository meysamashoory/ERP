from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("", include("catalog.urls")),
    path("", include("reports.urls")),
    path("", include("core.urls")),
    path("production/", include("production.urls")),
    path("planning/", include("planning.urls")),
    path("accounts/", include("accounts.urls")),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "سامانه برنامه ریزی و کنترل تولید"
admin.site.site_title = "برنامه‌ریزی تولید"
admin.site.index_title = "مدیریت داده‌ها"
