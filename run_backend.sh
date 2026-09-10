#!/bin/bash
echo "================================"
echo "  CogniSense AI - Backend Start"
echo "================================"

cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "Starting Flask backend on http://localhost:5000"
echo ""
python app.py