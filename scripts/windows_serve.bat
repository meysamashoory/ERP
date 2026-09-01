@echo off
REM ============================================================
REM  اجرای سرور پروداکشن روی ویندوز با Waitress
REM  Production server on Windows using Waitress (gunicorn does
REM  NOT run on Windows). Default port: 80.
REM  Override: set ERP_PORT=8080
REM ============================================================
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\activate.bat"

if "%ERP_PORT%"=="" set ERP_PORT=80

REM --- Production settings ---------------------------------
set DJANGO_DEBUG=False

REM Set a strong, secret key. Change this value for real deployments!
if "%DJANGO_SECRET_KEY%"=="" (
  echo [WARNING] DJANGO_SECRET_KEY is not set. Using an insecure default.
  echo           Set it before real use:  set DJANGO_SECRET_KEY=your-long-random-value
  set DJANGO_SECRET_KEY=change-me-please-set-a-real-secret-key
)

REM Hosts allowed to reach the server. Prefer explicit names/IPs in production:
REM   set DJANGO_ALLOWED_HOSTS=planning.poliran,192.168.1.50,localhost
if "%DJANGO_ALLOWED_HOSTS%"=="" set DJANGO_ALLOWED_HOSTS=planning.poliran,localhost,127.0.0.1
if "%DJANGO_CSRF_TRUSTED_ORIGINS%"=="" set DJANGO_CSRF_TRUSTED_ORIGINS=http://planning.poliran,http://planning.poliran:%ERP_PORT%

echo [1/3] Applying migrations ...
python manage.py migrate --noinput
if errorlevel 1 exit /b 1

echo [2/3] Collecting static files ...
python manage.py collectstatic --noinput
if errorlevel 1 exit /b 1

echo [3/3] Starting Waitress on http://0.0.0.0:%ERP_PORT%/
echo       Open from LAN: http://planning.poliran/
echo       NOTE: Port 80 usually needs "Run as administrator". If bind fails, set ERP_PORT=8080
waitress-serve --listen=0.0.0.0:%ERP_PORT% erp.wsgi:application
endlocal
