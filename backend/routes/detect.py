from flask import Blueprint, request, jsonify
import base64
import cv2
import numpy as np
import json

from database import get_db
from cognitive_engine import get_engine
from typing_metrics import get_typing_metrics

detect_bp = Blueprint('detect', __name__)


def _analyzer(uid):
    from mediapipe_engine import get_analyzer
    return get_analyzer(int(uid))


def _decode_frame(b64):
    try:
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        buf = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception as exc:
        print(f'[WARN] Frame decode failed: {exc}')
        return None


def _typing_from_request(uid, data):
    t = data.get('typing')
    tracker = get_typing_metrics(uid)
    if isinstance(t, dict):
        return tracker.record(t.get('keypress_count', 0), t.get('backspace_count', 0), t.get('timestamp'))
    return tracker.snapshot()


def _recs(result):
    recs = []
    state = result.get('state')
    cfi = result.get('cfi', 0) or 0
    blink = result.get('blink_rate', 0) or 0
    pause = result.get('pause_duration')
    if state == 'COGNITIVE_OVERLOAD':
        recs.append({'icon': '🧘', 'text': 'Take a short mental break', 'reason': 'Sustained cognitive overload detected'})
    elif state == 'FLOW_STATE':
        recs.append({'icon': '⚡', 'text': 'Keep your current study rhythm', 'reason': 'High engagement with efficient typing'})
    if cfi >= 85:
        recs.append({'icon': '☕', 'text': 'Take a 2-minute micro-break', 'reason': 'High cumulative cognitive strain'})
    if blink > 28:
        recs.append({'icon': '👁️', 'text': 'Rest your eyes briefly', 'reason': 'High blink-rate signal'})
    if pause is not None and pause > 4:
        recs.append({'icon': '🧩', 'text': 'Break the task into one step', 'reason': 'Long pause detected'})
    if not recs and state == 'NORMAL_STATE':
        recs.append({'icon': '🎯', 'text': 'Continue your current routine', 'reason': 'No sustained overload detected'})
    return recs[:4]


def _payload(result, live, typing, decision):
    result = result or {}
    state = decision.get('state', 'NORMAL_STATE') if decision else 'NORMAL_STATE'
    if not result:
        return {
            'state': state, 'focus_score': 0, 'stress': 0, 'distraction': 0,
            'face_detected': live.get('face_detected', False),
            'face_status': live.get('face_status', 'FACE_NOT_DETECTED'),
            'data_quality': live.get('data_quality', 0),
            'emotion': 'Unavailable', 'emotion_confidence': 0,
            'blink_rate': live.get('blink_rate', 0),
            'blink_total': live.get('blinks_session', 0), 'blinks_this_window': live.get('blinks_window', 0),
            'avg_blink_duration': live.get('avg_blink_duration', 0),
            'ear': live.get('ear', 0), 'ear_base': live.get('ear_base'),
            'brow_deviation': 0, 'gaze_jitter': live.get('gaze_jitter'), 'cli_vision': None,
            'kpm': typing.get('kpm'), 'backspace_ratio': typing.get('backspace_ratio'),
            'pause_duration': typing.get('pause_duration'), 'typing_available': typing.get('available', False),
            'cfi': decision.get('cfi', 0) if decision else 0,
            'calibration_status': live.get('calibration_status'), 'calibration_progress': live.get('calibration_progress', 0),
            'window_progress': live.get('window_progress', 0), 'window_secs_left': live.get('secs_left', 5),
            'is_observing': True, 'reasons': [], 'recommendations': [],
        }

    merged = dict(result)
    merged.update(decision or {})
    merged.update({
        'face_detected': live.get('face_detected', False),
        'face_status': live.get('face_status', result.get('face_status', 'FACE_NOT_DETECTED')),
        'data_quality': live.get('data_quality', result.get('data_quality', 0)),
        'ear': live.get('ear', result.get('avg_ear', 0)),
        'ear_base': live.get('ear_base'),
        'blink_total': live.get('blinks_session', result.get('blinks_session', 0)),
        'blinks_this_window': live.get('blinks_window', result.get('blinks_window', 0)),
        'blink_rate': result.get('blink_rate', live.get('blink_rate', 0)),
        'avg_blink_duration': result.get('avg_blink_duration', live.get('avg_blink_duration', 0)),
        'brow_live': live.get('brow_live'),
        'gaze_jitter': result.get('gaze_jitter', live.get('gaze_jitter')),
        'calibration_status': live.get('calibration_status'),
        'calibration_progress': live.get('calibration_progress', 0),
        'window_progress': live.get('window_progress', 0),
        'window_secs_left': live.get('secs_left', 5),
        'is_observing': not live.get('window_completed', False),
        'window_completed': live.get('window_completed', False),
        'recommendations': _recs(merged),
        'debug': {
            'face_status': live.get('face_status'), 'face_quality': live.get('data_quality'),
            'ear': live.get('ear'), 'ear_base': live.get('ear_base'),
            'blink_total': live.get('blinks_session'), 'blink_rate': live.get('blink_rate'),
            'brow_live': live.get('brow_live'), 'brow_base': live.get('brow_base'),
            'brow_deviation': merged.get('brow_deviation'), 'gaze_jitter': merged.get('gaze_jitter'),
            'cli_vision': merged.get('cli_vision'), 'kpm': typing.get('kpm'),
            'backspace_ratio': typing.get('backspace_ratio'), 'pause_duration': typing.get('pause_duration'),
            'state': state, 'cfi': merged.get('cfi', 0), 'reasons': merged.get('reasons', []),
        }
    })
    return merged


def _save(uid, sid, result, typing, decision):
    if not sid:
        return
    try:
        conn = get_db()
        conn.execute('''INSERT INTO detections
            (user_id,session_id,focus_score,stress_level,blink_rate,head_movement,
             eye_consistency,attention_score,cognitive_state,fake_detected,emotion,
             emotion_confidence,cli_vision,cfi,kpm,backspace_ratio,pause_duration,
             brow_deviation,gaze_jitter)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (uid, sid, result.get('focus_score', 0), result.get('stress', 0), result.get('blink_rate', 0),
             result.get('head_movement', ''), result.get('eye_consistency', 0), result.get('avg_attention', 0),
             decision.get('state', 'NORMAL_STATE'), 0, result.get('emotion', 'Unavailable'),
             result.get('emotion_confidence', 0), decision.get('cli_vision'), decision.get('cfi', 0),
             typing.get('kpm'), typing.get('backspace_ratio'), typing.get('pause_duration'),
             result.get('brow_deviation', 0), result.get('gaze_jitter', 0)))

        reasons = '; '.join(decision.get('reasons', []))
        conn.execute('''INSERT INTO cognitive_metrics
            (session_id,user_id,face_detected,face_status,data_quality,ear,blink_count,blink_rate,
             avg_blink_duration,brow_deviation,gaze_jitter,cli_vision,kpm,backspace_ratio,
             pause_duration,keypress_count,backspace_count,emotion,emotion_confidence,state,cfi,reasons)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sid, uid, int(result.get('face_detected', False)), result.get('face_status'), result.get('data_quality', 0),
             result.get('ear'), result.get('blink_total', 0), result.get('blink_rate'), result.get('avg_blink_duration', 0),
             result.get('brow_deviation', 0), result.get('gaze_jitter'), decision.get('cli_vision'), typing.get('kpm'),
             typing.get('backspace_ratio'), typing.get('pause_duration'), typing.get('keypress_count', 0),
             typing.get('backspace_count', 0), result.get('emotion', 'Unavailable'), result.get('emotion_confidence', 0),
             decision.get('state', 'NORMAL_STATE'), decision.get('cfi', 0), reasons))

        state = decision.get('state')
        if state == 'COGNITIVE_OVERLOAD':
            conn.execute('INSERT INTO alerts (user_id,session_id,alert_type,message,severity) VALUES(?,?,?,?,?)',
                         (uid, sid, 'cognitive_overload', 'High cognitive strain detected. A short break is recommended.', 'critical'))
        elif state == 'FLOW_STATE':
            # Do not spam success alerts; the state is visible on the dashboard.
            pass
        if decision.get('cfi', 0) >= 85:
            conn.execute('INSERT INTO alerts (user_id,session_id,alert_type,message,severity) VALUES(?,?,?,?,?)',
                         (uid, sid, 'fatigue', 'High cumulative cognitive strain detected. A short break is recommended.', 'warning'))
        conn.commit(); conn.close()
    except Exception as exc:
        print(f'[DB] telemetry save failed: {exc}')


@detect_bp.route('/detect', methods=['POST'])
def detect():
    data = request.get_json(silent=True) or {}
    uid = int(data.get('user_id', 1))
    sid = data.get('session_id')
    frame_b64 = data.get('frame')

    az = _analyzer(uid)
    typing = _typing_from_request(uid, data)
    frame = _decode_frame(frame_b64) if frame_b64 else None
    vision_result, _, live = az.process_frame(frame)
    vision_result = vision_result or {}
    if live.get('face_status') == 'MULTIPLE_FACES':
        vision_result = None

    decision = get_engine(uid).decide({**vision_result, **live}, typing) if vision_result else get_engine(uid).decide({**live, 'cli_vision': None}, typing)
    payload = _payload(vision_result, live, typing, decision)

    if live.get('window_completed') and vision_result and live.get('calibrated'):
        _save(uid, sid, payload, typing, decision)

    return jsonify({'success': True, 'data': payload})


@detect_bp.route('/detect/debug', methods=['GET'])
def debug_state():
    uid = request.args.get('user_id', 1, type=int)
    az = _analyzer(uid)
    live = az.last_live or az._make_live(False, az.ear_base or 0, 0, 0, False, az.last_face_status, az.last_data_quality)
    typing = get_typing_metrics(uid).snapshot()
    return jsonify({'success': True, 'debug': {**live, **typing}})


@detect_bp.route('/analyze', methods=['GET'])
def analyze():
    uid = request.args.get('user_id', 1, type=int)
    conn = get_db()
    rows = conn.execute('''SELECT state, COUNT(*) n, AVG(cli_vision) cli, AVG(cfi) cfi
                           FROM cognitive_metrics WHERE user_id=? GROUP BY state''', (uid,)).fetchall()
    conn.close()
    return jsonify({'success': True, 'distribution': {r['state']: {'count': r['n'], 'avg_cli': round(r['cli'] or 0, 1), 'avg_cfi': round(r['cfi'] or 0, 1)} for r in rows}})


@detect_bp.route('/session/reset', methods=['POST'])
def reset_session():
    data = request.get_json(silent=True) or {}
    uid = int(data.get('user_id', 1))
    from mediapipe_engine import reset_analyzer
    from cognitive_engine import reset_engine
    from typing_metrics import reset_typing_metrics
    reset_analyzer(uid); reset_engine(uid); reset_typing_metrics(uid)
    return jsonify({'success': True, 'message': 'Engine reset'})
