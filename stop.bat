@echo off
REM stop.bat — stop the dashboard (uvicorn + vite) AND the BTC_pricer_15m docker stack.

setlocal

echo [stop] killing uvicorn on port 8799 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8799 .*LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo [stop] killing vite on port 5174 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":5174 .*LISTENING"') do taskkill /F /PID %%a >nul 2>&1

echo [stop] docker compose down (BTC_pricer_15m: grid + live) ...
pushd "%~dp0..\BTC_pricer_15m"
docker compose down
popd

echo [stop] done.
endlocal
