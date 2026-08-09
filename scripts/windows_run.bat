@echo off
REM ============================================================
REM  اجرای سرور توسعه (Development) روی ویندوز
REM  Runs the Django development server on all interfaces.
REM  Open http://<server-ip>:8000/ from other machines on the LAN.
REM ============================================================
setlocal
cd /d "%~dp0.."
call ".venv\Scripts\activate.bat"

REM Allow access via the server's IP address. Adjust as needed.
if "%DJANGO_ALLOWED_HOSTS%"=="" set DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,*

python manage.py runserver 0.0.0.0:8000
endlocal
