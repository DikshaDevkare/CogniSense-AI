from mediapipe_engine import get_analyzer, reset_analyzer

def get_engine(user_id=1):
    return get_analyzer(user_id)

def reset_engine(user_id=1):
    reset_analyzer(user_id)
