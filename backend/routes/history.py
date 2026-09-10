# routes/history.py
from flask import Blueprint, request, jsonify
from database import get_db
from datetime import datetime

history_bp = Blueprint('history', __name__)

@history_bp.route('/history', methods=['GET'])
def get_history():
    user_id = request.args.get('user_id', 1, type=int)
    limit = request.args.get('limit', 20, type=int)

    conn = get_db()
    rows = conn.execute('''
        SELECT id, start_time, end_time, duration, focus_score,
               avg_stress, distraction_count, status
        FROM sessions
        WHERE user_id = ?
        ORDER BY start_time DESC
        LIMIT ?
    ''', (user_id, limit)).fetchall()
    conn.close()

    sessions = []
    for i, row in enumerate(rows):
        focus = round(row['focus_score'] or 0)
        stress_val = row['avg_stress'] or 0
        stress_label = 'High' if stress_val > 60 else ('Medium' if stress_val > 30 else 'Low')

        # Format duration from seconds
        dur_secs = row['duration'] or 0
        h = dur_secs // 3600
        m = (dur_secs % 3600) // 60
        s = dur_secs % 60
        duration_str = f"{h:02d}:{m:02d}:{s:02d}"

        # Parse date
        try:
            dt = datetime.fromisoformat(row['start_time'])
            date_str = dt.strftime('%d %b %Y')
        except Exception:
            date_str = row['start_time'] or 'N/A'

        status = row['status'] or ('Focused' if focus >= 65 else ('Stressed' if stress_val > 50 else 'Distracted'))

        sessions.append({
            'id': f"S{str(row['id']).zfill(3)}",
            'date': date_str,
            'duration': duration_str,
            'focus': focus,
            'status': status,
            'stress': stress_label
        })

    return jsonify({'success': True, 'sessions': sessions})


@history_bp.route('/history', methods=['POST'])
def save_session():
    data = request.get_json() or {}
    user_id = data.get('user_id', 1)
    duration = data.get('duration', 0)
    focus_score = data.get('focus_score', 0)
    avg_stress = data.get('avg_stress', 0)
    distraction_count = data.get('distraction_count', 0)

    status = 'Focused' if focus_score >= 65 else ('Stressed' if avg_stress > 50 else 'Distracted')

    conn = get_db()
    cur = conn.execute('''
        INSERT INTO sessions (user_id, duration, focus_score, avg_stress, distraction_count, status, end_time)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, duration, focus_score, avg_stress, distraction_count, status))
    session_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'session_id': session_id, 'status': status})


@history_bp.route('/history/<int:session_id>', methods=['GET'])
def get_session_detail(session_id):
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()

    session = conn.execute(
        'SELECT * FROM sessions WHERE id = ? AND user_id = ?',
        (session_id, user_id)
    ).fetchone()

    if not session:
        conn.close()
        return jsonify({'success': False, 'message': 'Session not found'}), 404

    detections = conn.execute('''
        SELECT timestamp, focus_score, stress_level, blink_rate,
               head_movement, cognitive_state, fake_detected
        FROM detections
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT 100
    ''', (session_id,)).fetchall()

    alerts = conn.execute('''
        SELECT alert_type, message, severity, timestamp
        FROM alerts WHERE session_id = ?
        ORDER BY timestamp DESC
    ''', (session_id,)).fetchall()

    conn.close()

    return jsonify({
        'success': True,
        'session': dict(session),
        'detections': [dict(d) for d in detections],
        'alerts': [dict(a) for a in alerts]
    })


@history_bp.route('/history/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()
    conn.execute('DELETE FROM sessions WHERE id = ? AND user_id = ?', (session_id, user_id))
    conn.execute('DELETE FROM detections WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Session deleted'})