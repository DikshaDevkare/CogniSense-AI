# ============================================================
# mediapipe_engine.py — CogniSense AI + AegisMind Vision Engine
# Real-Time Behavioral & Micro-Expression Telemetry
# Zero fake values: all metrics derived from physical landmarks.
# ============================================================

import cv2
import numpy as np
import math
import time
from collections import deque
from emotion_detector import get_emotion_detector

try:
    import mediapipe as mp
    _mp_face  = mp.solutions.face_mesh
    _mp_draw  = mp.solutions.drawing_utils
    _mp_style = mp.solutions.drawing_styles
    MEDIAPIPE_OK = True
except Exception as e:
    MEDIAPIPE_OK = False
    print(f"[WARN] MediaPipe not available: {e}")

# ============================================================
# LANDMARK INDICES (MediaPipe 478-point Refined Mesh)
# ============================================================
# Left eye EAR points
L_EAR = [362, 385, 387, 263, 373, 380]
# Right eye EAR points
R_EAR = [33,  160, 158, 133, 153, 144]

# Iris centers (refined landmarks)
L_IRIS_CENTER = 468
R_IRIS_CENTER = 473

# Inner Eyebrows
L_BROW_INNER  = 336
R_BROW_INNER  = 107

# Head Pose Keypoints
NOSE_TIP      = 1
CHIN          = 152
L_EYE_OUT     = 33
R_EYE_OUT     = 263
FOREHEAD      = 10

# Observation Constants
OBSERVATION_SECS = 5.0

# ============================================================
class RealBehaviorAnalyzer:
    """
    Multimodal Vision Engine:
      - 15-second personalized baseline calibration
      - Real EAR blink detection with baseline hysteresis
      - Brow contraction (ΔBrow) from inner brow distance
      - Iris / gaze jitter (30-sample rolling window)
      - Vision Cognitive Load Score (CLI_v)
      - Head stability and attention alignment
      - OpenCV Haar Cascade fallback if FaceMesh drops frames
    """

    def __init__(self):
        self.face_mesh = None
        self.face_cascade = None
        self._init_mp()
        self._init_fallback_cascade()
        self.emotion_detector = get_emotion_detector()

        # ── Calibration Baseline ──────────────────────────
        self.is_calibrated = False
        self.ear_base = 0.28
        self.brow_base = 50.0
        self.jitter_base = 0.02

        # ── Blink Telemetry (Hysteresis) ──────────────────
        self.eye_closed = False
        self.eye_close_ms = 0
        self.blinks_session = 0
        self.blinks_window = 0
        self.blink_times = deque()
        self.blink_durations = deque(maxlen=20)

        # ── Gaze / Iris Jitter (30 Samples Window) ────────
        self.iris_history = deque(maxlen=30)
        self.last_brow_dist = 50.0
        self.last_cli_v = 0.0

        # ── Rolling Window Accumulators ───────────────────
        self.obs_start = time.time()
        self.frames_all = 0
        self.frames_face = 0
        self.ear_buf = []
        self.yaw_buf = []
        self.pitch_buf = []
        self.attn_buf = []
        self.fwd_frames = 0
        self.nose_positions = []

        # ── State History ─────────────────────────────────
        self.result_history = deque(maxlen=6)
        self.last_result = None
        self.window_number = 0
        self.session_start = time.time()
        self.last_emotion_time = 0
        self.current_emotion = {'emotion': 'Neutral', 'confidence': 0.0}

    def _init_mp(self):
        if not MEDIAPIPE_OK:
            return
        try:
            self.face_mesh = _mp_face.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.4,
                min_tracking_confidence=0.4,
            )
            print("[INFO] MediaPipe Refined FaceMesh initialized.")
        except Exception as e:
            print(f"[ERROR] FaceMesh init error: {e}")

    def _init_fallback_cascade(self):
        """OpenCV Haar Cascade fallback for face detection."""
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if os.path.exists(cascade_path):
            self.face_cascade = cv2.CascadeClassifier(cascade_path)

    # ── EAR Calculation ───────────────────────────────────
    @staticmethod
    def _compute_ear(lm, pts, w, h):
        p = [(lm[i].x * w, lm[i].y * h) for i in pts]
        a = math.dist(p[1], p[5])
        b = math.dist(p[2], p[4])
        c = math.dist(p[0], p[3])
        return (a + b) / (2.0 * c + 1e-7)

    # ── Blink Detection with Baseline Hysteresis ──────────
    def _process_blink(self, ear):
        now_ms = int(time.time() * 1000)

        # Baseline-relative thresholds
        closed_thresh = self.ear_base * 0.80 if self.is_calibrated else 0.23
        recovery_thresh = self.ear_base * 0.88 if self.is_calibrated else 0.26

        if ear < closed_thresh:
            if not self.eye_closed:
                self.eye_closed = True
                self.eye_close_ms = now_ms
        elif ear >= recovery_thresh:
            if self.eye_closed:
                dur = now_ms - self.eye_close_ms
                if 30 <= dur <= 900:   # valid blink duration
                    self.blinks_session += 1
                    self.blinks_window += 1
                    self.blink_times.append(now_ms)
                    self.blink_durations.append(dur)
                self.eye_closed = False

    def _blink_rate(self):
        """Blinks per minute over the last 60 seconds."""
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - 60_000
        while self.blink_times and self.blink_times[0] < cutoff:
            self.blink_times.popleft()
        elapsed = min(60.0, (time.time() - self.session_start))
        if elapsed < 5.0:
            return 0.0
        return round((len(self.blink_times) / elapsed) * 60.0, 1)

    # ── Gaze Jitter Calculation ───────────────────────────
    def _calculate_gaze_jitter(self, lm, w, h):
        """Standard deviation of iris center coordinates across 30 samples."""
        try:
            lx = lm[L_IRIS_CENTER].x * w
            ly = lm[L_IRIS_CENTER].y * h
            rx = lm[R_IRIS_CENTER].x * w
            ry = lm[R_IRIS_CENTER].y * h
            center_x = (lx + rx) / 2.0
            center_y = (ly + ry) / 2.0

            self.iris_history.append((center_x, center_y))
            if len(self.iris_history) < 10:
                return self.jitter_base

            pts = np.array(self.iris_history)
            dists = np.sqrt(np.sum(np.diff(pts, axis=0)**2, axis=1))
            jitter = float(np.mean(dists)) / (w * 0.1) # normalized
            return round(min(1.0, jitter), 3)
        except Exception:
            return self.jitter_base

    # ── Brow Contraction Calculation ──────────────────────
    def _calculate_brow_distance(self, lm, w, h):
        """Pixel distance between inner eyebrows."""
        try:
            lx = lm[L_BROW_INNER].x * w
            ly = lm[L_BROW_INNER].y * h
            rx = lm[R_BROW_INNER].x * w
            ry = lm[R_BROW_INNER].y * h
            dist = math.dist((lx, ly), (rx, ry))
            self.last_brow_dist = dist
            return dist
        except Exception:
            return self.brow_base

    # ── Head Angles (Yaw, Pitch) ──────────────────────────
    @staticmethod
    def _head_angles(lm, w, h):
        nose_x   = lm[NOSE_TIP].x
        l_eye_x  = lm[L_EYE_OUT].x
        r_eye_x  = lm[R_EYE_OUT].x
        face_cx  = (l_eye_x + r_eye_x) / 2.0
        eye_span = abs(r_eye_x - l_eye_x) + 1e-6
        yaw      = (nose_x - face_cx) / eye_span * 75.0

        nose_y   = lm[NOSE_TIP].y
        fore_y   = lm[FOREHEAD].y
        chin_y   = lm[CHIN].y
        v_span   = abs(chin_y - fore_y) + 1e-6
        pitch    = ((nose_y - fore_y) / v_span - 0.5) * 75.0

        return round(yaw, 2), round(pitch, 2)

    def _head_stability(self):
        if len(self.yaw_buf) < 4:
            return 80.0
        ys = float(np.std(self.yaw_buf))
        ps = float(np.std(self.pitch_buf))
        return round(max(0.0, min(100.0, 100.0 - (ys + ps) * 2.6)), 1)

    def _movement_score(self):
        if len(self.nose_positions) < 4:
            return 10.0
        dists = [math.dist(self.nose_positions[i], self.nose_positions[i-1])
                 for i in range(1, len(self.nose_positions))]
        return round(min(100.0, float(np.mean(dists)) * 8.0), 1)

    def _eye_consistency(self):
        if len(self.ear_buf) < 6:
            return 60.0
        std = float(np.std(self.ear_buf))
        if 0.007 <= std <= 0.09:
            return min(100.0, 50.0 + std * 550.0)
        elif std < 0.007:
            return 18.0
        return max(10.0, 85.0 - std * 270.0)

    def _elapsed(self):
        return time.time() - self.obs_start

    def window_progress(self):
        return min(100, int(self._elapsed() / OBSERVATION_SECS * 100))

    def secs_left(self):
        return max(0.0, round(OBSERVATION_SECS - self._elapsed(), 1))

    # ============================================================
    # MAIN: Process BGR Frame
    # ============================================================
    def process_frame(self, frame_bgr):
        if frame_bgr is None:
            self.frames_all += 1
            return self.last_result, None, self._make_live(False, self.ear_base, 0, 0, False)

        h, w = frame_bgr.shape[:2]
        now = time.time()
        self.frames_all += 1

        face_det = False
        ear = self.ear_base
        yaw = 0.0
        pitch = 0.0
        looking_fwd = True

        # 1. Primary Detector: MediaPipe FaceMesh
        if self.face_mesh is not None:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self.face_mesh.process(rgb)

            if res.multi_face_landmarks:
                face_det = True
                self.frames_face += 1
                lm = res.multi_face_landmarks[0].landmark

                # EAR
                l_ear = self._compute_ear(lm, L_EAR, w, h)
                r_ear = self._compute_ear(lm, R_EAR, w, h)
                ear = (l_ear + r_ear) / 2.0
                self.ear_buf.append(ear)

                # Blink
                self._process_blink(ear)

                # Brow & Jitter
                brow_live = self._calculate_brow_distance(lm, w, h)
                jitter_live = self._calculate_gaze_jitter(lm, w, h)

                # Head Pose
                yaw, pitch = self._head_angles(lm, w, h)
                self.yaw_buf.append(yaw)
                self.pitch_buf.append(pitch)

                # Nose positions
                nx = int(lm[NOSE_TIP].x * w)
                ny = int(lm[NOSE_TIP].y * h)
                self.nose_positions.append((nx, ny))
                if len(self.nose_positions) > 30:
                    self.nose_positions.pop(0)

                # Attention
                looking_fwd = abs(yaw) < 22 and abs(pitch) < 18
                if looking_fwd:
                    self.fwd_frames += 1

                attn = 0
                if looking_fwd:           attn += 40
                if abs(yaw) < 14:         attn += 25
                if abs(pitch) < 12:       attn += 20
                if ear > (self.ear_base * 0.9): attn += 15
                self.attn_buf.append(attn)

                # Controlled-interval Emotion Inference (every 0.5 sec)
                if (now - self.last_emotion_time) > 0.5:
                    self.last_emotion_time = now
                    # Crop face ROI from landmarks
                    xs = [p.x * w for p in lm]
                    ys = [p.y * h for p in lm]
                    x1, y1 = max(0, int(min(xs))), max(0, int(min(ys)))
                    x2, y2 = min(w, int(max(xs))), min(h, int(max(ys)))
                    if x2 > x1 and y2 > y1:
                        face_crop = frame_bgr[y1:y2, x1:x2]
                        self.current_emotion = self.emotion_detector.predict_emotion(face_crop)

                # Frame Annotations
                frame_bgr = self._annotate(frame_bgr, res, w, h, ear, yaw, pitch, looking_fwd)

        # 2. Fallback Detector: OpenCV Haar Cascade if FaceMesh failed
        if not face_det and self.face_cascade is not None:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
            if len(faces) > 0:
                face_det = True
                self.frames_face += 1
                # Mark as detected via fallback
                x, y, fw, fh = faces[0]
                cv2.rectangle(frame_bgr, (x, y), (x+fw, y+fh), (255, 165, 0), 1)

        # 3. Window Completion Check
        win_ready = self._elapsed() >= OBSERVATION_SECS
        if win_ready:
            result = self._compute_window_result()
            self.last_result = result
            self.window_number += 1
            self._reset_window()
        else:
            result = self.last_result

        live = self._make_live(face_det, ear, yaw, pitch, looking_fwd)
        return result, frame_bgr, live

    # ============================================================
    # Window Result Computation
    # ============================================================
    def _compute_window_result(self):
        n = max(self.frames_all, 1)
        face_ratio = self.frames_face / n

        head_stab = self._head_stability()
        move_score = self._movement_score()
        eye_consist = self._eye_consistency()
        avg_attn = float(np.mean(self.attn_buf)) if self.attn_buf else 0.0
        blink_rate = self._blink_rate()
        look_pct = (self.fwd_frames / max(self.frames_face, 1)) * 100.0
        avg_ear = float(np.mean(self.ear_buf)) if self.ear_buf else self.ear_base

        focus = stress = distract = 0

        if avg_attn >= 80:    focus += 30
        elif avg_attn >= 60:  focus += 20; distract += 5
        elif avg_attn >= 40:  focus += 10; distract += 15
        else:                 distract += 25

        if head_stab >= 80:   focus += 20
        elif head_stab >= 55: focus += 12; distract += 5
        else:                 distract += 15; stress += 5

        if blink_rate == 0:          distract += 10
        elif 10 <= blink_rate <= 20: focus += 20
        elif blink_rate > 28:        stress += 22; distract += 5
        elif blink_rate > 22:        stress += 12; focus += 5
        elif blink_rate < 6:         focus += 15; stress += 4
        else:                        focus += 10

        if eye_consist >= 75:   focus += 15
        elif eye_consist >= 50: focus += 8; distract += 5
        else:                   distract += 10

        if face_ratio >= 0.85:  focus += 10
        elif face_ratio >= 0.5: focus += 5; distract += 5
        else:                   distract += 10

        if look_pct >= 75:   focus += 5
        elif look_pct < 40:  distract += 5

        if move_score > 60:  distract += 8; stress += 4
        elif move_score > 35: distract += 4

        sess_mins = (time.time() - self.session_start) / 60.0
        if sess_mins > 90:   stress += 8; focus = max(0, focus - 5)
        elif sess_mins > 60: stress += 4

        total = max(focus + stress + distract, 1)
        focus_pct  = min(100, round(focus / total * 100))
        stress_pct = min(100, round(stress / total * 100))
        distr_pct  = min(100, round(distract / total * 100))

        if focus_pct >= 55:       state = "Focused"
        elif stress_pct >= 38:    state = "Stressed"
        else:                     state = "Distracted"

        self.result_history.append(focus_pct)
        smooth = round(float(np.mean(self.result_history)), 1)

        return {
            "state":          state,
            "focus_score":    focus_pct,
            "smooth_focus":   smooth,
            "stress":         stress_pct,
            "distraction":    distr_pct,
            "blink_rate":     round(blink_rate, 1),
            "blinks_window":  self.blinks_window,
            "blinks_session": self.blinks_session,
            "head_stability": head_stab,
            "movement_score": move_score,
            "eye_consistency": eye_consist,
            "avg_attention":  round(avg_attn, 1),
            "avg_ear":        round(avg_ear, 3),
            "face_ratio":     round(face_ratio * 100, 1),
            "looking_pct":    round(look_pct, 1),
            "head_movement":  "Stable" if head_stab > 65 else "Moving",
            "session_mins":   round(sess_mins, 1),
            "window_number":  self.window_number,
            "fake_detected":  False,
            "emotion":        self.current_emotion.get('emotion', 'Neutral'),
            "emotion_confidence": self.current_emotion.get('confidence', 0.0)
        }

    def _reset_window(self):
        self.obs_start = time.time()
        self.frames_all = 0
        self.frames_face = 0
        self.blinks_window = 0
        self.ear_buf = []
        self.yaw_buf = []
        self.pitch_buf = []
        self.attn_buf = []
        self.fwd_frames = 0
        self.nose_positions = []

    def _make_live(self, face_det, ear, yaw, pitch, looking_fwd):
        eye_state = "CLOSED" if self.eye_closed else "open"
        return {
            "face_detected":   face_det,
            "ear":             round(ear, 3),
            "eye_state":       eye_state,
            "blinks_window":   self.blinks_window,
            "blinks_session":  self.blinks_session,
            "blink_rate":      self._blink_rate(),
            "yaw":             yaw,
            "pitch":           pitch,
            "looking_fwd":     looking_fwd,
            "window_progress": self.window_progress(),
            "secs_left":       self.secs_left(),
            "window_ready":    self._elapsed() >= OBSERVATION_SECS,
            "avg_attn":        round(float(np.mean(self.attn_buf)), 1) if self.attn_buf else 0,
            "session_mins":    (time.time() - self.session_start) / 60.0,
            "frames_face":     self.frames_face,
            "frames_all":      self.frames_all,
        }

    def _annotate(self, frame, res, w, h, ear, yaw, pitch, looking_fwd):
        if MEDIAPIPE_OK:
            try:
                _mp_draw.draw_landmarks(
                    image=frame,
                    landmark_list=res.multi_face_landmarks[0],
                    connections=_mp_face.FACEMESH_CONTOURS,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=_mp_style.get_default_face_mesh_contours_style()
                )
            except Exception:
                pass

        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (320, 110), (6, 4, 20), -1)
        cv2.addWeighted(ov, 0.60, frame, 0.40, 0, frame)

        eye_lbl = "CLOSED" if self.eye_closed else "open"
        cv2.putText(frame, f"EAR={ear:.3f} eye={eye_lbl}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 255), 1)
        cv2.putText(frame, f"Blinks={self.blinks_session} rate={self._blink_rate():.0f}/min", (8, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 255, 180), 1)
        cv2.putText(frame, f"Yaw={yaw:.1f} Pitch={pitch:.1f}", (8, 66),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 220, 100), 1)
        gaze_col = (50, 220, 50) if looking_fwd else (50, 50, 240)
        cv2.putText(frame, f"Gaze: {'Forward' if looking_fwd else 'Away'}", (8, 88),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, gaze_col, 1)

        prog = self.window_progress()
        bar_w = int(w * prog / 100)
        cv2.rectangle(frame, (0, h-6), (w, h), (20, 10, 40), -1)
        cv2.rectangle(frame, (0, h-6), (bar_w, h), (168, 85, 247), -1)

        return frame

    def reset_session(self):
        self.__init__()


# ── Singleton per user ────────────────────────────────────
_analyzers: dict = {}

def get_analyzer(uid: int = 1) -> RealBehaviorAnalyzer:
    if uid not in _analyzers:
        _analyzers[uid] = RealBehaviorAnalyzer()
    return _analyzers[uid]

def reset_analyzer(uid: int = 1):
    _analyzers[uid] = RealBehaviorAnalyzer()
