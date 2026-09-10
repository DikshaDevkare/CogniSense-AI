@echo off
echo ================================
echo  CogniSense AI - Frontend Start
echo ================================
echo.
echo Opening frontend on http://localhost:3000
echo.

cd /d "%~dp0frontend"
start http://localhost:3000
python -m http.server 3000

pause