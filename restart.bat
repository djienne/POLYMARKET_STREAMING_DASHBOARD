@echo off
REM restart.bat — stop then start both the dashboard and the BTC_pricer_15m containers.

call "%~dp0stop.bat"
timeout /t 2 /nobreak >nul
call "%~dp0start.bat"
