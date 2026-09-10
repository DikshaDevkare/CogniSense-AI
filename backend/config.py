# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cognisense-secret-2024')
    DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'cognisense.db')
    DEBUG = True
    DETECTION_INTERVAL = 2.5   # seconds between AI checks
    BLINK_THRESHOLD = 25        # blinks/min = high
    HEAD_MOVEMENT_THRESHOLD = 15
    FOCUS_DROP_THRESHOLD = 40
    STRESS_THRESHOLD = 60