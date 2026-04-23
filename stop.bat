@echo off
REM stop.bat - stop the dashboard and the BTC_pricer_15m paper grid.
REM Live trading is controlled only by live_switch.ps1.

setlocal

echo [stop] killing uvicorn on port 8799 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8799 .*LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo [stop] killing vite on port 5174 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":5174 .*LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo [stop] docker compose stop grid ...
pushd "%~dp0..\BTC_pricer_15m"
docker compose stop grid
popd

echo [stop] done.
endlocal
