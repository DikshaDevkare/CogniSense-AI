from flask import Blueprint, request, jsonify, Response
from database import get_db
from datetime import datetime
import csv
import io
import json

history_bp = Blueprint('history', __name__)


def _status(focus, stress, state=None):
    if state in ('COGNITIVE_OVERLOAD', 'Stressed'):
        return 'Stressed'
    if state in ('FLOW_STATE', 'Focused') or focus >= 65:
        return 'Focused'
    return 'Distracted'


def _session_export(user_id, session_id):
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
    if not session:
        conn.close()
        return None
    metrics = conn.execute('SELECT * FROM cognitive_metrics WHERE session_id=? ORDER BY timestamp ASC', (session_id,)).fetchall()
    detections = conn.execute('SELECT * FROM detections WHERE session_id=? ORDER BY timestamp ASC', (session_id,)).fetchall()
    alerts = conn.execute('SELECT * FROM alerts WHERE session_id=? ORDER BY timestamp ASC', (session_id,)).fetchall()
    conn.close()
    from session_storage import write_session_files
    return write_session_files(user_id, session, metrics, detections, alerts)


@history_bp.route('/session/start', methods=['POST'])
def start_session():
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id', 1))
    from mediapipe_engine import reset_analyzer
    from cognitive_engine import reset_engine
    from typing_metrics import reset_typing_metrics
    reset_analyzer(user_id); reset_engine(user_id); reset_typing_metrics(user_id)
    conn = get_db()
    cur = conn.execute('INSERT INTO sessions (user_id, start_time) VALUES (?, CURRENT_TIMESTAMP)', (user_id,))
    session_id = cur.lastrowid
    conn.commit()
    row = conn.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
    conn.close()
    return jsonify({'success': True, 'session_id': session_id, 'session': dict(row)})


@history_bp.route('/session/end', methods=['POST'])
def end_session():
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id', 1))
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'message': 'session_id is required'}), 400
    session_id = int(session_id)

    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
    if not session:
        conn.close()
        return jsonify({'success': False, 'message': 'Session not found'}), 404

    agg = conn.execute('''
        SELECT AVG(focus_score) avg_focus,
               AVG(stress_level) avg_stress,
               AVG(cli_vision) avg_cli,
               AVG(cfi) avg_cfi,
               MAX(cfi) max_cfi,
               SUM(CASE WHEN cognitive_state IN ('Distracted','COGNITIVE_OVERLOAD') THEN 1 ELSE 0 END) distractions,
               MAX(blink_count) total_blinks
        FROM cognitive_metrics WHERE session_id=?
    ''', (session_id,)).fetchone()
    end_time = datetime.now().isoformat(timespec='seconds')
    start = datetime.fromisoformat(str(session['start_time']).replace('Z', '')) if session['start_time'] else datetime.now()
    duration = max(0, int((datetime.now() - start).total_seconds()))
    focus = round(agg['avg_focus'] or 0, 1)
    stress = round(agg['avg_stress'] or 0, 1)
    state = 'COGNITIVE_OVERLOAD' if (agg['max_cfi'] or 0) >= 85 else None
    status = _status(focus, stress, state)

    conn.execute('''UPDATE sessions SET end_time=?, duration=?, focus_score=?, avg_stress=?,
                    distraction_count=?, status=?, avg_cognitive_load=?, avg_cfi=?, total_blinks=?
                    WHERE id=? AND user_id=?''',
                 (end_time, duration, focus, stress, int(agg['distractions'] or 0), status,
                  round(agg['avg_cli'] or 0, 1), round(agg['avg_cfi'] or 0, 1), int(agg['total_blinks'] or 0), session_id, user_id))
    conn.commit()
    row = conn.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
    conn.close()

    paths = _session_export(user_id, session_id)
    return jsonify({'success': True, 'session_id': session_id, 'session': dict(row), 'files': paths or []})


@history_bp.route('/history', methods=['GET'])
def get_history():
    user_id = request.args.get('user_id', 1, type=int)
    limit = min(100, max(1, request.args.get('limit', 20, type=int)))
    conn = get_db()
    rows = conn.execute('''SELECT id, start_time, end_time, duration, focus_score,
                           avg_stress, distraction_count, status, avg_cognitive_load,
                           avg_cfi, total_blinks
                           FROM sessions WHERE user_id=? ORDER BY start_time DESC LIMIT ?''', (user_id, limit)).fetchall()
    conn.close()

    sessions = []
    for row in rows:
        try:
            dt = datetime.fromisoformat(str(row['start_time']))
            date_str = dt.strftime('%d %b %Y')
        except Exception:
            date_str = str(row['start_time'] or 'N/A')
        dur = int(row['duration'] or 0)
        stress = float(row['avg_stress'] or 0)
        sessions.append({
            'id': f"S{int(row['id']):03d}", 'session_id': int(row['id']), 'date': date_str,
            'duration': f'{dur//3600:02d}:{(dur%3600)//60:02d}:{dur%60:02d}',
            'focus': round(float(row['focus_score'] or 0)),
            'status': row['status'] or 'Unknown',
            'stress': 'High' if stress > 60 else ('Medium' if stress > 30 else 'Low'),
            'avg_cognitive_load': round(float(row['avg_cognitive_load'] or 0), 1),
            'avg_cfi': round(float(row['avg_cfi'] or 0), 1),
            'total_blinks': int(row['total_blinks'] or 0),
        })
    return jsonify({'success': True, 'sessions': sessions})


@history_bp.route('/history', methods=['POST'])
def save_session_compat():
    """Compatibility endpoint for older frontend versions; creates a completed session."""
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id', 1))
    conn = get_db()
    cur = conn.execute('''INSERT INTO sessions
        (user_id, duration, focus_score, avg_stress, distraction_count, status, end_time)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''',
        (user_id, int(data.get('duration', 0) or 0), float(data.get('focus_score', 0) or 0),
         float(data.get('avg_stress', 0) or 0), int(data.get('distraction_count', 0) or 0),
         _status(float(data.get('focus_score', 0) or 0), float(data.get('avg_stress', 0) or 0))))
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    _session_export(user_id, sid)
    return jsonify({'success': True, 'session_id': sid})


@history_bp.route('/history/<int:session_id>', methods=['GET'])
def get_session_detail(session_id):
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
    if not session:
        conn.close(); return jsonify({'success': False, 'message': 'Session not found'}), 404
    metrics = conn.execute('SELECT * FROM cognitive_metrics WHERE session_id=? ORDER BY timestamp ASC', (session_id,)).fetchall()
    detections = conn.execute('SELECT * FROM detections WHERE session_id=? ORDER BY timestamp ASC LIMIT 500', (session_id,)).fetchall()
    alerts = conn.execute('SELECT * FROM alerts WHERE session_id=? ORDER BY timestamp DESC', (session_id,)).fetchall()
    conn.close()
    return jsonify({'success': True, 'session': dict(session), 'metrics': [dict(x) for x in metrics], 'detections': [dict(x) for x in detections], 'alerts': [dict(x) for x in alerts]})


@history_bp.route('/history/<int:session_id>/export.csv', methods=['GET'])
def export_session_csv(session_id):
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE id=? AND user_id=?', (session_id, user_id)).fetchone()
    if not session:
        conn.close(); return jsonify({'success': False, 'message': 'Session not found'}), 404
    rows = conn.execute('SELECT * FROM cognitive_metrics WHERE session_id=? ORDER BY timestamp ASC', (session_id,)).fetchall()
    conn.close()
    output = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ['session_id']
    writer = csv.DictWriter(output, fieldnames=fieldnames); writer.writeheader()
    for row in rows: writer.writerow(dict(row))
    content=output.getvalue()
    from config import Config
    import os
    os.makedirs(Config.EXPORT_DIR,exist_ok=True)
    with open(os.path.join(Config.EXPORT_DIR,f'session_{session_id}.csv'),'w',encoding='utf-8',newline='') as fh: fh.write(content)
    return Response(content, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=session_{session_id}.csv'})


@history_bp.route('/history/export.csv', methods=['GET'])
def export_all_sessions_csv():
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()
    rows = conn.execute('''SELECT id, start_time, end_time, duration, focus_score, avg_stress,
                           distraction_count, status, avg_cognitive_load, avg_cfi, total_blinks
                           FROM sessions WHERE user_id=? ORDER BY start_time DESC''', (user_id,)).fetchall()
    conn.close()
    output = io.StringIO(); fields = ['id','start_time','end_time','duration','focus_score','avg_stress','distraction_count','status','avg_cognitive_load','avg_cfi','total_blinks']
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for row in rows: writer.writerow(dict(row))
    content=output.getvalue()
    from config import Config
    import os
    os.makedirs(Config.EXPORT_DIR,exist_ok=True)
    with open(os.path.join(Config.EXPORT_DIR,f'cognisense_sessions_{user_id}.csv'),'w',encoding='utf-8',newline='') as fh: fh.write(content)
    return Response(content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=cognisense_sessions.csv'})


@history_bp.route('/history/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    user_id = request.args.get('user_id', 1, type=int)
    conn = get_db()
    conn.execute('DELETE FROM alerts WHERE session_id=? AND user_id=?', (session_id, user_id))
    conn.execute('DELETE FROM cognitive_metrics WHERE session_id=? AND user_id=?', (session_id, user_id))
    conn.execute('DELETE FROM detections WHERE session_id=? AND user_id=?', (session_id, user_id))
    conn.execute('DELETE FROM sessions WHERE id=? AND user_id=?', (session_id, user_id))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'message': 'Session deleted'})
