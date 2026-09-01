@echo off
REM ============================================================
REM  اجرای سرور توسعه (Development) روی ویندوز
REM  Runs the Django development server on all interfaces.
REM  Default port: 80  →  http://planning.poliran/
REM  Override: set ERP_PORT=8080
REM ============================================================
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\activate.bat"

if "%ERP_PORT%"=="" set ERP_PORT=80

REM Allow access via LAN IP and intranet hostname planning.poliran
if "%DJANGO_ALLOWED_HOSTS%"=="" set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,planning.poliran,*
if "%DJANGO_CSRF_TRUSTED_ORIGINS%"=="" set DJANGO_CSRF_TRUSTED_ORIGINS=http://planning.poliran,http://planning.poliran:%ERP_PORT%

echo Starting ERP on http://0.0.0.0:%ERP_PORT%/  (LAN: http://planning.poliran/)
echo NOTE: Port 80 usually needs "Run as administrator". If bind fails, set ERP_PORT=8080
python manage.py runserver 0.0.0.0:%ERP_PORT%
endlocal
