# CogniSense AI + AegisMind vision engine
import os
import cv2
import numpy as np
import math
import time
from collections import deque

from config import Config
from emotion_detector import get_emotion_detector

try:
    import mediapipe as mp
    _mp_face = mp.solutions.face_mesh
    _mp_draw = mp.solutions.drawing_utils
    _mp_style = mp.solutions.drawing_styles
    MEDIAPIPE_OK = True
except Exception as e:
    MEDIAPIPE_OK = False
    print(f'[WARN] MediaPipe not available: {e}')

L_EAR = [362, 385, 387, 263, 373, 380]
R_EAR = [33, 160, 158, 133, 153, 144]
L_IRIS_CENTER = 468
R_IRIS_CENTER = 473
L_BROW_INNER = 336
R_BROW_INNER = 107
NOSE_TIP = 1
CHIN = 152
L_EYE_OUT = 33
R_EYE_OUT = 263
FOREHEAD = 10
OBSERVATION_SECS = Config.OBSERVATION_SECS


class RealBehaviorAnalyzer:
    def __init__(self):
        self.face_mesh = None
        self.face_cascade = None
        self._init_mp()
        self._init_fallback_cascade()
        self.emotion_detector = get_emotion_detector()
        self._reset_state()

    def _reset_state(self):
        # Session state
        self.session_start = time.monotonic()
        self.obs_start = time.monotonic()
        self.window_number = 0
        self.last_result = None
        self.result_history = deque(maxlen=6)

        # Calibration
        self.calibration_start = time.monotonic()
        self.is_calibrated = False
        self.calibration_complete = False
        self.calibration_ear = []
        self.calibration_brow = []
        self.calibration_jitter = []
        self.ear_base = None
        self.brow_base = None
        self.jitter_base = None

        # Blink telemetry
        self.eye_closed = False
        self.eye_close_ms = 0
        self.blinks_session = 0
        self.blinks_window = 0
        self.blink_times = deque()
        self.blink_durations = deque(maxlen=50)

        # Rolling measurements
        self.iris_history = deque(maxlen=Config.JITTER_SAMPLES)
        self.ear_buf = []
        self.yaw_buf = []
        self.pitch_buf = []
        self.attn_buf = []
        self.fwd_frames = 0
        self.nose_positions = deque(maxlen=30)
        self.frames_all = 0
        self.frames_face = 0
        self.frames_invalid = 0
        self.last_face_status = 'FACE_NOT_DETECTED'
        self.last_data_quality = 0.0
        self.last_emotion_time = 0.0
        self.current_emotion = {'emotion': 'Unavailable', 'confidence': 0.0, 'model_used': False}
        self.last_live = {}
        self.current_brow_live = None
        self.current_jitter_live = None

    def _init_mp(self):
        if not MEDIAPIPE_OK:
            return
        try:
            self.face_mesh = _mp_face.FaceMesh(
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=0.4,
                min_tracking_confidence=0.4,
            )
            print('[INFO] MediaPipe Refined FaceMesh initialized.')
        except Exception as e:
            self.face_mesh = None
            print(f'[ERROR] FaceMesh init error: {e}')

    def _init_fallback_cascade(self):
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if os.path.exists(cascade_path):
            self.face_cascade = cv2.CascadeClassifier(cascade_path)

    @staticmethod
    def _compute_ear(lm, pts, w, h):
        p = [(lm[i].x * w, lm[i].y * h) for i in pts]
        a = math.dist(p[1], p[5])
        b = math.dist(p[2], p[4])
        c = math.dist(p[0], p[3])
        return (a + b) / (2.0 * c + 1e-7)

    def _process_blink(self, ear):
        now_ms = int(time.monotonic() * 1000)
        base = self.ear_base if self.is_calibrated and self.ear_base else 0.28
        closed_thresh = base * Config.EAR_CLOSED_FACTOR
        recovery_thresh = base * Config.EAR_RECOVERY_FACTOR

        if ear < closed_thresh:
            if not self.eye_closed:
                self.eye_closed = True
                self.eye_close_ms = now_ms
            return

        if ear >= recovery_thresh and self.eye_closed:
            duration = now_ms - self.eye_close_ms
            self.eye_closed = False
            if Config.BLINK_MIN_MS <= duration <= Config.BLINK_MAX_MS:
                # Exactly one increment per closed -> recovered transition.
                self.blinks_session += 1
                self.blinks_window += 1
                self.blink_times.append(now_ms)
                self.blink_durations.append(duration)

    def _blink_rate(self):
        now_ms = int(time.monotonic() * 1000)
        cutoff = now_ms - 60_000
        while self.blink_times and self.blink_times[0] < cutoff:
            self.blink_times.popleft()
        elapsed = min(60.0, time.monotonic() - self.session_start)
        if elapsed <= 0 or not self.blink_times:
            return 0.0
        return round((len(self.blink_times) / elapsed) * 60.0, 1)

    def _calculate_gaze_jitter(self, lm, w, h):
        try:
            lx, ly = lm[L_IRIS_CENTER].x * w, lm[L_IRIS_CENTER].y * h
            rx, ry = lm[R_IRIS_CENTER].x * w, lm[R_IRIS_CENTER].y * h
            center = ((lx + rx) / 2.0, (ly + ry) / 2.0)
            self.iris_history.append(center)
            if len(self.iris_history) < 10:
                return self.jitter_base or 0.0
            pts = np.asarray(self.iris_history, dtype=np.float32)
            step_dist = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
            return round(float(np.mean(step_dist)) / max(w * 0.1, 1.0), 4)
        except Exception:
            return self.jitter_base or 0.0

    def _calculate_brow_distance(self, lm, w, h):
        lx, ly = lm[L_BROW_INNER].x * w, lm[L_BROW_INNER].y * h
        rx, ry = lm[R_BROW_INNER].x * w, lm[R_BROW_INNER].y * h
        return math.dist((lx, ly), (rx, ry))

    @staticmethod
    def _head_angles(lm, w, h):
        nose_x = lm[NOSE_TIP].x
        l_eye_x = lm[L_EYE_OUT].x
        r_eye_x = lm[R_EYE_OUT].x
        face_cx = (l_eye_x + r_eye_x) / 2.0
        eye_span = abs(r_eye_x - l_eye_x) + 1e-6
        yaw = (nose_x - face_cx) / eye_span * 75.0
        nose_y, fore_y, chin_y = lm[NOSE_TIP].y, lm[FOREHEAD].y, lm[CHIN].y
        v_span = abs(chin_y - fore_y) + 1e-6
        pitch = ((nose_y - fore_y) / v_span - 0.5) * 75.0
        return round(yaw, 2), round(pitch, 2)

    def _head_stability(self):
        if len(self.yaw_buf) < 4:
            return 80.0
        return round(max(0.0, min(100.0, 100.0 - (float(np.std(self.yaw_buf)) + float(np.std(self.pitch_buf))) * 2.6)), 1)

    def _movement_score(self):
        if len(self.nose_positions) < 4:
            return 10.0
        dists = [math.dist(self.nose_positions[i], self.nose_positions[i - 1]) for i in range(1, len(self.nose_positions))]
        return round(min(100.0, float(np.mean(dists)) * 8.0), 1)

    def _eye_consistency(self):
        if len(self.ear_buf) < 6:
            return 60.0
        std = float(np.std(self.ear_buf))
        if 0.007 <= std <= 0.09:
            return min(100.0, 50.0 + std * 550.0)
        if std < 0.007:
            return 18.0
        return max(10.0, 85.0 - std * 270.0)

    def _elapsed(self):
        return time.monotonic() - self.obs_start

    def window_progress(self):
        return min(100, int(self._elapsed() / OBSERVATION_SECS * 100))

    def secs_left(self):
        return max(0.0, round(OBSERVATION_SECS - self._elapsed(), 1))

    # ---------------- Calibration ----------------
    def _update_calibration(self, ear, brow, jitter):
        if self.is_calibrated:
            return
        if ear is not None:
            self.calibration_ear.append(float(ear))
        if brow is not None:
            self.calibration_brow.append(float(brow))
        if jitter is not None and jitter > 0:
            self.calibration_jitter.append(float(jitter))

        elapsed = time.monotonic() - self.calibration_start
        if elapsed < Config.CALIBRATION_SECS:
            return

        if len(self.calibration_ear) < Config.MIN_CALIBRATION_FRAMES or len(self.calibration_brow) < Config.MIN_CALIBRATION_FRAMES:
            self.calibration_complete = False
            # Safely retry with a fresh window; never invent a baseline.
            self.calibration_ear.clear(); self.calibration_brow.clear(); self.calibration_jitter.clear()
            self.calibration_start = time.monotonic()
            print('[CALIBRATION] insufficient valid frames; retrying 15-second baseline.')
            return

        self.ear_base = float(np.median(self.calibration_ear))
        self.brow_base = float(np.median(self.calibration_brow))
        self.jitter_base = float(np.median(self.calibration_jitter)) if self.calibration_jitter else 0.0
        if self.ear_base <= 0 or self.brow_base <= 0:
            self.calibration_complete = False
            return
        self.is_calibrated = True
        self.calibration_complete = True
        print(f'[CALIBRATION] complete frames={len(self.calibration_ear)} EAR={self.ear_base:.4f} Brow={self.brow_base:.2f} Jitter={self.jitter_base:.4f}')

    def calibration_status(self):
        elapsed = time.monotonic() - self.calibration_start
        if self.is_calibrated:
            return 'COMPLETE', 100.0
        if elapsed < Config.CALIBRATION_SECS:
            return 'CALIBRATING', min(100.0, elapsed / Config.CALIBRATION_SECS * 100.0)
        return 'INCOMPLETE', 100.0

    # ---------------- Main processing ----------------
    def process_frame(self, frame_bgr):
        self.frames_all += 1
        if frame_bgr is None:
            self.frames_invalid += 1
            live = self._make_live(False, self.ear_base or 0.0, 0.0, 0.0, False, 'FACE_NOT_DETECTED', 0.0)
            return self.last_result, None, live

        h, w = frame_bgr.shape[:2]
        face_det = False
        face_status = 'FACE_NOT_DETECTED'
        quality = 0.0
        ear = self.ear_base or 0.0
        yaw = pitch = 0.0
        looking_fwd = False
        brow_live = None
        jitter_live = None

        if self.face_mesh is not None:
            try:
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                res = self.face_mesh.process(rgb)
                faces = res.multi_face_landmarks or []
                if len(faces) > 1:
                    face_status = 'MULTIPLE_FACES'
                    self.frames_invalid += 1
                elif len(faces) == 1:
                    face_det = True
                    face_status = 'FACE_DETECTED'
                    self.frames_face += 1
                    lm = faces[0].landmark
                    xs = np.asarray([p.x for p in lm])
                    ys = np.asarray([p.y for p in lm])
                    bbox_area = max(0.0, (xs.max() - xs.min()) * (ys.max() - ys.min()))
                    quality = max(0.0, min(100.0, bbox_area * 1000.0))
                    if quality < 8:
                        face_status = 'LOW_CONFIDENCE'
                        face_det = False
                        self.frames_invalid += 1
                    else:
                        l_ear = self._compute_ear(lm, L_EAR, w, h)
                        r_ear = self._compute_ear(lm, R_EAR, w, h)
                        ear = (l_ear + r_ear) / 2.0
                        self.ear_buf.append(ear)
                        self._process_blink(ear)
                        brow_live = self._calculate_brow_distance(lm, w, h)
                        jitter_live = self._calculate_gaze_jitter(lm, w, h)
                        self.current_brow_live = brow_live
                        self.current_jitter_live = jitter_live
                        self._update_calibration(ear, brow_live, jitter_live)
                        yaw, pitch = self._head_angles(lm, w, h)
                        self.yaw_buf.append(yaw); self.pitch_buf.append(pitch)
                        nx, ny = int(lm[NOSE_TIP].x * w), int(lm[NOSE_TIP].y * h)
                        self.nose_positions.append((nx, ny))
                        looking_fwd = abs(yaw) < 22 and abs(pitch) < 18
                        if looking_fwd:
                            self.fwd_frames += 1
                        attn = 40 if looking_fwd else 0
                        if abs(yaw) < 14: attn += 25
                        if abs(pitch) < 12: attn += 20
                        if self.ear_base and ear > self.ear_base * 0.9: attn += 15
                        self.attn_buf.append(attn)

                        if time.monotonic() - self.last_emotion_time > 0.5:
                            self.last_emotion_time = time.monotonic()
                            x1, y1 = max(0, int(xs.min() * w)), max(0, int(ys.min() * h))
                            x2, y2 = min(w, int(xs.max() * w)), min(h, int(ys.max() * h))
                            if x2 > x1 and y2 > y1:
                                self.current_emotion = self.emotion_detector.predict_emotion(frame_bgr[y1:y2, x1:x2])

                        try:
                            _mp_draw.draw_landmarks(
                                image=frame_bgr,
                                landmark_list=faces[0],
                                connections=_mp_face.FACEMESH_CONTOURS,
                                landmark_drawing_spec=None,
                                connection_drawing_spec=_mp_style.get_default_face_mesh_contours_style()
                            )
                        except Exception:
                            pass
            except Exception as e:
                self.frames_invalid += 1
                face_status = 'LOW_CONFIDENCE'
                print(f'[FACE] MediaPipe frame error: {e}')

        # Haar is only a detection fallback. It does not invent landmark metrics.
        if not face_det and self.face_cascade is not None:
            try:
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
                if len(faces) == 1:
                    face_status = 'FACE_DETECTED_FALLBACK'
                    x, y, fw, fh = faces[0]
                    cv2.rectangle(frame_bgr, (x, y), (x + fw, y + fh), (255, 165, 0), 1)
                    quality = min(100.0, max(10.0, (fw * fh) / max(w * h, 1) * 1000))
                elif len(faces) > 1:
                    face_status = 'MULTIPLE_FACES'
            except Exception as e:
                print(f'[FACE] Haar fallback error: {e}')

        self.last_face_status = face_status
        self.last_data_quality = round(quality, 1)

        win_ready = self._elapsed() >= OBSERVATION_SECS
        window_completed = False
        if win_ready:
            result = self._compute_window_result(face_det)
            self.last_result = result
            self.window_number += 1
            self._reset_window()
            window_completed = True
        else:
            result = self.last_result

        live = self._make_live(face_det, ear, yaw, pitch, looking_fwd, face_status, quality, brow_live, jitter_live)
        live['window_completed'] = window_completed
        self.last_live = live
        return result, frame_bgr, live

    def _compute_window_result(self, face_det):
        n = max(self.frames_all, 1)
        face_ratio = self.frames_face / n
        head_stab = self._head_stability()
        move_score = self._movement_score()
        eye_consist = self._eye_consistency()
        avg_attn = float(np.mean(self.attn_buf)) if self.attn_buf else 0.0
        blink_rate = self._blink_rate()
        look_pct = (self.fwd_frames / max(self.frames_face, 1)) * 100.0
        avg_ear = float(np.mean(self.ear_buf)) if self.ear_buf else (self.ear_base or 0.0)

        if self.is_calibrated and self.ear_base and self.brow_base:
            delta_ear = max(0.0, (self.ear_base - avg_ear) / self.ear_base)
            brow_live = float(np.median(self.calibration_brow[-10:])) if self.calibration_brow else self.brow_base
            # Use the current window's latest brow when available.
            # Calibration values are retained separately; last_live carries current brow.
            brow_live = self.current_brow_live if self.current_brow_live is not None else brow_live
            delta_brow = max(0.0, (self.brow_base - brow_live) / self.brow_base)
        else:
            delta_ear = 0.0
            delta_brow = 0.0

        jitter_live = self.current_jitter_live
        jitter_live = float(jitter_live) if jitter_live is not None else 0.0
        cli_v = min(100.0, (0.50 * delta_brow + 0.30 * jitter_live + 0.20 * delta_ear) * 250.0) if self.is_calibrated else None

        # Legacy scores remain available for the existing dashboard.
        focus = 0; stress = 0; distract = 0
        if avg_attn >= 80: focus += 30
        elif avg_attn >= 60: focus += 20; distract += 5
        elif avg_attn >= 40: focus += 10; distract += 15
        else: distract += 25
        if head_stab >= 80: focus += 20
        elif head_stab >= 55: focus += 12; distract += 5
        else: distract += 15; stress += 5
        if blink_rate == 0: distract += 10
        elif 10 <= blink_rate <= 20: focus += 20
        elif blink_rate > 28: stress += 22; distract += 5
        elif blink_rate > 22: stress += 12; focus += 5
        elif blink_rate < 6: focus += 15; stress += 4
        else: focus += 10
        if eye_consist >= 75: focus += 15
        elif eye_consist >= 50: focus += 8; distract += 5
        else: distract += 10
        if face_ratio >= 0.85: focus += 10
        elif face_ratio >= 0.5: focus += 5; distract += 5
        else: distract += 10
        if look_pct >= 75: focus += 5
        elif look_pct < 40: distract += 5
        if move_score > 60: distract += 8; stress += 4
        elif move_score > 35: distract += 4

        total = max(focus + stress + distract, 1)
        focus_pct = min(100, round(focus / total * 100))
        stress_pct = min(100, round(stress / total * 100))
        distract_pct = min(100, round(distract / total * 100))
        self.result_history.append(focus_pct)

        return {
            'state': 'Analyzing...',  # Dual-stream engine replaces this with the authoritative state.
            'focus_score': focus_pct,
            'smooth_focus': round(float(np.mean(self.result_history)), 1),
            'stress': stress_pct,
            'distraction': distract_pct,
            'blink_rate': round(blink_rate, 1),
            'blinks_window': self.blinks_window,
            'blinks_session': self.blinks_session,
            'avg_blink_duration': round(float(np.mean(self.blink_durations)), 1) if self.blink_durations else 0.0,
            'head_stability': head_stab,
            'movement_score': move_score,
            'eye_consistency': eye_consist,
            'avg_attention': round(avg_attn, 1),
            'avg_ear': round(avg_ear, 3),
            'face_ratio': round(face_ratio * 100, 1),
            'looking_pct': round(look_pct, 1),
            'head_movement': 'Stable' if head_stab > 65 else 'Moving',
            'session_mins': round((time.monotonic() - self.session_start) / 60.0, 1),
            'window_number': self.window_number,
            'fake_detected': False,
            'emotion': self.current_emotion.get('emotion', 'Unavailable'),
            'emotion_confidence': self.current_emotion.get('confidence', 0.0),
            'emotion_model_used': self.current_emotion.get('model_used', False),
            'brow_deviation': round(delta_brow, 4),
            'delta_ear': round(delta_ear, 4),
            'gaze_jitter': round(jitter_live, 4),
            'cli_vision': round(cli_v, 1) if cli_v is not None else None,
            'face_status': self.last_face_status,
            'data_quality': self.last_data_quality,
            'calibrated': self.is_calibrated,
        }

    def _reset_window(self):
        self.obs_start = time.monotonic()
        self.frames_all = 0
        self.frames_face = 0
        self.frames_invalid = 0
        self.blinks_window = 0
        self.ear_buf = []
        self.yaw_buf = []
        self.pitch_buf = []
        self.attn_buf = []
        self.fwd_frames = 0
        self.nose_positions.clear()
        self.iris_history.clear()
        self.current_brow_live = None
        self.current_jitter_live = None

    def _make_live(self, face_det, ear, yaw, pitch, looking_fwd, face_status, quality, brow_live=None, jitter_live=None):
        status, cal_progress = self.calibration_status()
        return {
            'face_detected': face_det,
            'face_status': face_status,
            'data_quality': round(quality, 1),
            'ear': round(float(ear or 0), 3),
            'eye_state': 'CLOSED' if self.eye_closed else 'open',
            'blinks_window': self.blinks_window,
            'blinks_session': self.blinks_session,
            'blink_rate': self._blink_rate(),
            'avg_blink_duration': round(float(np.mean(self.blink_durations)), 1) if self.blink_durations else 0.0,
            'yaw': round(float(yaw), 2),
            'pitch': round(float(pitch), 2),
            'looking_fwd': bool(looking_fwd),
            'window_progress': self.window_progress(),
            'secs_left': self.secs_left(),
            'window_ready': self._elapsed() >= OBSERVATION_SECS,
            'avg_attn': round(float(np.mean(self.attn_buf)), 1) if self.attn_buf else 0,
            'session_mins': (time.monotonic() - self.session_start) / 60.0,
            'frames_face': self.frames_face,
            'frames_all': self.frames_all,
            'calibration_status': status,
            'calibration_progress': round(cal_progress, 1),
            'calibrated': self.is_calibrated,
            'ear_base': round(self.ear_base, 4) if self.ear_base else None,
            'brow_base': round(self.brow_base, 2) if self.brow_base else None,
            'jitter_base': round(self.jitter_base, 4) if self.jitter_base is not None else None,
            'brow_live': round(float(brow_live), 2) if brow_live is not None else None,
            'gaze_jitter': round(float(jitter_live), 4) if jitter_live is not None else None,
        }

    def reset_session(self):
        self._reset_state()


_analyzers = {}


def get_analyzer(uid=1):
    uid = int(uid)
    if uid not in _analyzers:
        _analyzers[uid] = RealBehaviorAnalyzer()
    return _analyzers[uid]


def reset_analyzer(uid=1):
    _analyzers[int(uid)] = RealBehaviorAnalyzer()
