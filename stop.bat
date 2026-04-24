@echo off
REM stop.bat - compatibility wrapper for the Python manager.
python "%~dp0manage.py" stop %*
exit /b %ERRORLEVEL%
