import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cognisense-secret-2024')
    DATABASE = os.environ.get('COGNISENSE_DATABASE', str(BASE_DIR / 'database' / 'cognisense.db'))
    SESSION_DATA_DIR = os.environ.get('SESSION_DATA_DIR', str(BASE_DIR / 'session_data'))
    EXPORT_DIR = os.environ.get('EXPORT_DIR', str(BASE_DIR / 'exports'))
    DEBUG = os.environ.get('FLASK_DEBUG', '1') == '1'

    # Existing detection timing
    DETECTION_INTERVAL = 2.5
    OBSERVATION_SECS = 5.0

    # AegisMind personalized vision thresholds
    CALIBRATION_SECS = 15.0
    MIN_CALIBRATION_FRAMES = 30
    JITTER_SAMPLES = 30
    EAR_CLOSED_FACTOR = 0.80
    EAR_RECOVERY_FACTOR = 0.88
    BLINK_MIN_MS = 30
    BLINK_MAX_MS = 900

    # Dual-stream decision thresholds
    CLI_NORMAL_MAX = 45.0
    CLI_FLOW_MAX = 75.0
    FLOW_KPM_MIN = 90.0
    FLOW_BSR_MAX = 0.08
    OVERLOAD_BSR_MIN = 0.20
    OVERLOAD_PAUSE_SECS = 4.0
    OVERLOAD_SUSTAINED_SECS = 3.0

    # Cumulative fatigue
    CFI_ALPHA = 0.15
    CFI_LAMBDA = 0.005
    CFI_ALERT = 85.0

    # Optional LLM triage
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'none').lower()
