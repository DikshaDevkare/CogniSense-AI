from flask import Blueprint, request, jsonify
import base64, cv2, numpy as np, time
from database import get_db

detect_bp = Blueprint('detect', __name__)


def _analyzer(uid):
    from mediapipe_engine import get_analyzer
    return get_analyzer(int(uid))


def _decode_frame(b64: str):
    try:
        if ',' in b64:
            b64 = b64.split(',')[1]
        buf = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[WARN] Frame decode: {e}")
        return None


def _recs(result, live):
    recs  = []
    state = result.get('state', '')
    br    = result.get('blink_rate', 0)
    mins  = result.get('session_mins', 0)
    stab  = result.get('head_stability', 100)

    if mins > 45:
        recs.append({'icon':'☕','text':'Take a 5-min break',
                     'reason':f'{int(mins)} min of study'})
    if 0 < br < 8:
        recs.append({'icon':'👁️','text':'Blink more frequently',
                     'reason':'Eye strain risk detected'})
    if br > 26:
        recs.append({'icon':'🧘','text':'Deep breathing exercise',
                     'reason':'High blink rate — possible stress'})
    if state == 'Distracted':
        recs.append({'icon':'🎯','text':'Try Pomodoro technique',
                     'reason':'Focus is inconsistent'})
    if state == 'Stressed':
        recs.append({'icon':'💆','text':'Short mental break',
                     'reason':'Stress signals detected'})
    if stab < 50:
        recs.append({'icon':'📐','text':'Sit still and focus',
                     'reason':'Excessive head movement'})
    if not live.get('looking_fwd', True):
        recs.append({'icon':'📺','text':'Look at the screen',
                     'reason':'Gaze detected off-screen'})
    if not recs:
        recs.append({'icon':'🏆','text':'Keep it up!',
                     'reason':'Excellent performance'})
    return recs[:4]


def _payload(result, live):
    """Build full JSON payload for dashboard."""

    # While first window hasn't completed yet
    if not result:
        wp = live.get('window_progress', 0)
        sl = live.get('secs_left', 5)
        return {
            'state':'Analyzing...','focus_score':0,'smooth_focus':0,
            'stress':0,'distraction':0,'fake_detected':False,
            'blink_rate':0,'blinks_this_window':0,'blink_total':0,
            'head_movement':'Initializing','head_stability':0,
            'movement_score':0,'eye_consistency':0,'attention':0,
            'looking_forward':False,'face_ratio':0,
            'face_detected': live.get('face_detected', False),
            'emotion':'Analyzing','emotion_confidence':0,
            'window_progress':wp,'window_secs_left':sl,
            'window_number':0,'is_observing':True,
            'session_mins':0,'recommendations':[],

            # DEBUG fields
            'debug': {
                'ear':          live.get('ear', 0),
                'eye_state':    live.get('eye_state', 'unknown'),
                'blinks_session': live.get('blinks_session', 0),
                'blink_rate':   live.get('blink_rate', 0),
                'yaw':          live.get('yaw', 0),
                'pitch':        live.get('pitch', 0),
                'looking_fwd':  live.get('looking_fwd', False),
                'avg_attn':     live.get('avg_attn', 0),
                'frames_face':  live.get('frames_face', 0),
                'frames_all':   live.get('frames_all', 0),
                'face_detected':live.get('face_detected', False),
            }
        }

    return {
        # ── Cognitive state ──────────────────────────────
        'state':              result.get('state', 'Analyzing...'),
        'focus_score':        result.get('focus_score', 0),
        'smooth_focus':       result.get('smooth_focus', 0),
        'stress':             result.get('stress', 0),
        'distraction':        result.get('distraction', 0),
        'fake_detected':      result.get('fake_detected', False),

        # ── Behavioral metrics ───────────────────────────
        'blink_rate':         result.get('blink_rate', 0),
        'blinks_this_window': live.get('blinks_window', 0),
        'blink_total':        live.get('blinks_session', 0),
        'head_movement':      result.get('head_movement', 'Stable'),
        'head_stability':     result.get('head_stability', 0),
        'movement_score':     result.get('movement_score', 0),
        'eye_consistency':    result.get('eye_consistency', 0),
        'attention':          result.get('avg_attention', 0),
        'looking_forward':    live.get('looking_fwd', True),
        'face_ratio':         result.get('face_ratio', 0),
        'face_detected':      live.get('face_detected', False),

        # ── Emotion (derived from state) ─────────────────
        'emotion':            result.get('state', 'Neutral'),
        'emotion_confidence': result.get('focus_score', 0),

        # ── Observation window ───────────────────────────
        'window_progress':    live.get('window_progress', 0),
        'window_secs_left':   live.get('secs_left', 5),
        'window_number':      result.get('window_number', 0),
        'is_observing':       not live.get('window_ready', False),

        # ── Session ──────────────────────────────────────
        'session_mins':       result.get('session_mins', 0),

        # ── Recommendations ──────────────────────────────
        'recommendations':    _recs(result, live),

        # ── DEBUG panel (visible in API response) ────────
        'debug': {
            'ear':            live.get('ear', 0),
            'eye_state':      live.get('eye_state', 'unknown'),
            'blinks_session': live.get('blinks_session', 0),
            'blinks_window':  live.get('blinks_window', 0),
            'blink_rate':     live.get('blink_rate', 0),
            'yaw':            live.get('yaw', 0),
            'pitch':          live.get('pitch', 0),
            'looking_fwd':    live.get('looking_fwd', False),
            'avg_attn':       live.get('avg_attn', 0),
            'frames_face':    live.get('frames_face', 0),
            'frames_all':     live.get('frames_all', 0),
            'face_detected':  live.get('face_detected', False),
            'window_progress':live.get('window_progress', 0),
        }
    }


def _save(uid, sid, result):
    try:
        c = get_db()
        c.execute('''
            INSERT INTO detections
              (user_id,session_id,focus_score,stress_level,blink_rate,
               head_movement,eye_consistency,attention_score,
               cognitive_state,fake_detected)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (uid, sid,
             result.get('focus_score',0), result.get('stress',0),
             result.get('blink_rate',0),  result.get('head_movement',''),
             result.get('eye_consistency',0), result.get('avg_attention',0),
             result.get('state',''), int(result.get('fake_detected',False))))

        state  = result.get('state','')
        stress = result.get('stress',0)

        if state == 'Stressed' and stress > 45:
            c.execute('''INSERT INTO alerts
                (user_id,session_id,alert_type,message,severity)
                VALUES(?,?,?,?,?)''',
                (uid,sid,'stress','High stress detected. Take a breath.','critical'))
        if state == 'Distracted':
            c.execute('''INSERT INTO alerts
                (user_id,session_id,alert_type,message,severity)
                VALUES(?,?,?,?,?)''',
                (uid,sid,'focus','Distraction detected — refocus.','info'))

        c.commit(); c.close()
    except Exception as e:
        print(f"[DB] {e}")


# ============================================================
# POST /api/detect
# ============================================================
@detect_bp.route('/detect', methods=['POST'])
def detect():
    data    = request.get_json(silent=True) or {}
    uid     = int(data.get('user_id', 1))
    sid     = data.get('session_id')
    b64     = data.get('frame')

    az = _analyzer(uid)

    if b64:
        frame = _decode_frame(b64)
        result, _, live = az.process_frame(frame)
    else:
        result, _, live = az.process_frame(None)

    if live and live.get('window_ready') and result:
        _save(uid, sid, result)

    return jsonify({'success': True, 'data': _payload(result, live)})


# ============================================================
# GET /api/detect/debug  — real-time debug values
# ============================================================
@detect_bp.route('/detect/debug', methods=['GET'])
def debug_state():
    uid = request.args.get('user_id', 1, type=int)
    az  = _analyzer(uid)
    live = az._make_live(False, 0, 0, 0, False)
    return jsonify({
        'success': True,
        'debug': {
            'ear':            live['ear'],
            'eye_state':      live['eye_state'],
            'blinks_session': live['blinks_session'],
            'blink_rate':     live['blink_rate'],
            'yaw':            live['yaw'],
            'pitch':          live['pitch'],
            'looking_fwd':    live['looking_fwd'],
            'window_progress':live['window_progress'],
            'secs_left':      live['secs_left'],
            'frames_face':    live['frames_face'],
            'frames_all':     live['frames_all'],
        }
    })


# ============================================================
# GET /api/analyze
# ============================================================
@detect_bp.route('/analyze', methods=['GET'])
def analyze():
    uid  = request.args.get('user_id', 1, type=int)
    conn = get_db()
    rows = conn.execute('''
        SELECT cognitive_state,
               AVG(focus_score) AS af, AVG(stress_level) AS as_, COUNT(*) AS n
        FROM detections WHERE user_id=?
        GROUP BY cognitive_state''', (uid,)).fetchall()
    conn.close()
    dist = {r['cognitive_state']: {
        'count':r['n'],'avg_focus':round(r['af'] or 0,1),
        'avg_stress':round(r['as_'] or 0,1)} for r in rows}
    return jsonify({'success':True,'distribution':dist})


# ============================================================
# POST /api/session/reset
# ============================================================
@detect_bp.route('/session/reset', methods=['POST'])
def reset_session():
    data = request.get_json(silent=True) or {}
    uid  = int(data.get('user_id', 1))
    from mediapipe_engine import reset_analyzer
    reset_analyzer(uid)
    return jsonify({'success':True,'message':'Engine reset'})
