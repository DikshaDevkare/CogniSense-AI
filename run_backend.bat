@echo off
echo ================================
echo   CogniSense AI - Backend Start
echo ================================

cd /d "%~dp0backend"

IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting Flask backend...
echo Backend will run on: http://localhost:5000
echo.
python app.py

pause