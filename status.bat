@echo off
REM status.bat - compatibility wrapper for the Python manager.
python "%~dp0manage.py" status %*
exit /b %ERRORLEVEL%
