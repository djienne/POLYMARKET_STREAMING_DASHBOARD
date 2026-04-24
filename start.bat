@echo off
REM start.bat - compatibility wrapper for the Python manager.
python "%~dp0manage.py" start %*
exit /b %ERRORLEVEL%
