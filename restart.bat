@echo off
REM restart.bat - compatibility wrapper for the Python manager.
python "%~dp0manage.py" restart %*
exit /b %ERRORLEVEL%
