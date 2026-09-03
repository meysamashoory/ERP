@echo off
REM ============================================================
REM  اجرای سرور توسعه (Development) روی ویندوز
REM  Runs the Django development server on all interfaces.
REM  Open http://planning.poliran:8000/ from other machines on the LAN.
REM ============================================================
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\activate.bat"

REM Allow access via LAN IP and intranet hostname planning.poliran
if "%DJANGO_ALLOWED_HOSTS%"=="" set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,planning.poliran,*
if "%DJANGO_CSRF_TRUSTED_ORIGINS%"=="" set DJANGO_CSRF_TRUSTED_ORIGINS=http://planning.poliran:8000,http://planning.poliran

echo Starting ERP on http://0.0.0.0:8000/  (LAN: http://planning.poliran:8000/)
python manage.py runserver 0.0.0.0:8000
endlocal
