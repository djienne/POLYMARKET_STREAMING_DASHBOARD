@echo off
REM restart.bat - restart the dashboard and BTC_pricer_15m paper grid.
REM Live trading is controlled only by live_switch.ps1.

call "%~dp0stop.bat"
timeout /t 2 /nobreak >nul
call "%~dp0start.bat"
