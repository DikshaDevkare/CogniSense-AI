# TensorFlow/Keras FER-style emotion inference. No fake/random fallback.
import os
from collections import deque

import cv2
import numpy as np

try:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    from tensorflow import keras
    TF_AVAILABLE = True
except Exception as exc:
    TF_AVAILABLE = False
    print(f'[WARN] TensorFlow unavailable: {exc}')

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'emotion_model.h5')
EMOTION_LABELS = ['Angry', 'Happy', 'Sad', 'Neutral']
IMG_SIZE = 48

EMOTION_COGNITIVE_WEIGHTS = {
    'Happy': {'focus': 0.80, 'stress': 0.05, 'distraction': 0.15},
    'Neutral': {'focus': 0.65, 'stress': 0.10, 'distraction': 0.25},
    'Sad': {'focus': 0.25, 'stress': 0.45, 'distraction': 0.30},
    'Angry': {'focus': 0.15, 'stress': 0.70, 'distraction': 0.15},
}


class EmotionDetector:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.emotion_history = deque(maxlen=10)
        self._load_model()

    def _load_model(self):
        if not TF_AVAILABLE:
            return
        if not os.path.exists(MODEL_PATH):
            print(f'[WARN] Emotion model not found: {MODEL_PATH}')
            print('       Emotion output will be Unavailable until the model is trained.')
            return
        try:
            model = keras.models.load_model(MODEL_PATH)
            output_units = int(model.output_shape[-1])
            if output_units != len(EMOTION_LABELS):
                raise ValueError(f'Expected {len(EMOTION_LABELS)} output classes, got {output_units}')
            self.model = model
            self.model_loaded = True
            print(f'[INFO] Emotion model loaded: {MODEL_PATH}')
        except Exception as exc:
            print(f'[ERROR] Could not load emotion model: {exc}')

    def preprocess_face(self, face_roi):
        if face_roi is None or face_roi.size == 0:
            raise ValueError('Empty face ROI')
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY) if face_roi.ndim == 3 else face_roi
        resized = cv2.resize(gray, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
        normalized = resized.astype(np.float32) / 255.0
        return normalized.reshape(1, IMG_SIZE, IMG_SIZE, 1)

    def predict_emotion(self, face_roi):
        if not self.model_loaded:
            return self._unavailable('Model unavailable')
        try:
            preds = self.model.predict(self.preprocess_face(face_roi), verbose=0)[0]
            idx = int(np.argmax(preds))
            emotion = EMOTION_LABELS[idx]
            confidence = float(preds[idx]) * 100.0
            scores = {label: round(float(preds[i]) * 100.0, 1) for i, label in enumerate(EMOTION_LABELS)}
            self.emotion_history.append(emotion)
            return {
                'emotion': emotion,
                'smoothed_emotion': self._get_smoothed_emotion(),
                'confidence': round(confidence, 1),
                'all_scores': scores,
                'model_used': True,
                'available': True,
            }
        except Exception as exc:
            print(f'[ERROR] Emotion prediction failed: {exc}')
            return self._unavailable('Prediction failed')

    def _get_smoothed_emotion(self):
        if not self.emotion_history:
            return 'Unavailable'
        return max(set(self.emotion_history), key=list(self.emotion_history).count)

    @staticmethod
    def _unavailable(reason):
        return {
            'emotion': 'Unavailable',
            'smoothed_emotion': 'Unavailable',
            'confidence': 0.0,
            'all_scores': {},
            'model_used': False,
            'available': False,
            'reason': reason,
        }

    def get_cognitive_impact(self, emotion):
        return EMOTION_COGNITIVE_WEIGHTS.get(emotion, {'focus': 0.0, 'stress': 0.0, 'distraction': 0.0})

    def reset_history(self):
        self.emotion_history.clear()


_emotion_detector_instance = None


def get_emotion_detector():
    global _emotion_detector_instance
    if _emotion_detector_instance is None:
        _emotion_detector_instance = EmotionDetector()
    return _emotion_detector_instance
