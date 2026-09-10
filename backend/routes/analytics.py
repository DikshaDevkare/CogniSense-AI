from flask import Blueprint, request, jsonify, Response
from database import get_db
from datetime import datetime, timedelta
import csv
import io
import os
from config import Config

analytics_bp = Blueprint('analytics', __name__)


def fmt_dur(secs):
    secs = int(secs or 0)
    return f'{secs//3600:02d}:{(secs%3600)//60:02d}:{secs%60:02d}'


def _since(period):
    now = datetime.now()
    if period == 'week': return now - timedelta(days=7)
    if period == 'month': return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@analytics_bp.route('/analytics/summary', methods=['GET'])
def summary():
    uid = request.args.get('user_id', 1, type=int)
    period = request.args.get('period', 'today')
    since = _since(period).isoformat()
    now = datetime.now()
    conn = get_db()

    stats = conn.execute('''SELECT COUNT(*) total, AVG(focus_score) avg_focus, SUM(duration) total_dur,
                            AVG(avg_stress) avg_stress, SUM(distraction_count) total_dist,
                            MAX(focus_score) best, AVG(avg_cognitive_load) avg_cli, AVG(avg_cfi) avg_cfi,
                            SUM(total_blinks) total_blinks
                            FROM sessions WHERE user_id=? AND start_time>=?''', (uid, since)).fetchone()

    y_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    y_end = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    yest = conn.execute('SELECT AVG(focus_score) af, COUNT(*) n FROM sessions WHERE user_id=? AND start_time>=? AND start_time<?', (uid, y_start, y_end)).fetchone()

    trend = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        ds = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        de = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        row = conn.execute('''SELECT AVG(focus_score) af, AVG(avg_stress) as_, AVG(avg_cognitive_load) cli,
                              SUM(duration) dur, COUNT(*) n FROM sessions
                              WHERE user_id=? AND start_time>=? AND start_time<=?''', (uid, ds, de)).fetchone()
        trend.append({'day': day.strftime('%a'), 'focus': round(row['af'] or 0, 1), 'stress': round(row['as_'] or 0, 1), 'cognitive_load': round(row['cli'] or 0, 1), 'sessions': row['n'] or 0, 'duration': row['dur'] or 0})

    dist_rows = conn.execute('SELECT state, COUNT(*) n FROM cognitive_metrics WHERE user_id=? AND timestamp>=? GROUP BY state', (uid, since)).fetchall()
    state_counts = {r['state']: r['n'] for r in dist_rows}
    total_det = sum(state_counts.values())
    distribution = {s: round(state_counts.get(s, 0) / total_det * 100, 1) if total_det else 0 for s in ('NORMAL_STATE','FLOW_STATE','COGNITIVE_OVERLOAD')}

    emo_rows = conn.execute('''SELECT emotion, COUNT(*) n FROM cognitive_metrics
                               WHERE user_id=? AND timestamp>=? AND emotion IN ('Happy','Sad','Angry','Neutral') GROUP BY emotion''', (uid, since)).fetchall()
    emo_counts = {r['emotion']: r['n'] for r in emo_rows}; emo_total = sum(emo_counts.values())
    emotion_distribution = {e: round(emo_counts.get(e, 0) / emo_total * 100, 1) if emo_total else 0 for e in ('Happy','Neutral','Sad','Angry')}
    conn.close()

    avg_focus = round(stats['avg_focus'] or 0, 1)
    return jsonify({'success': True, 'period': period, 'stats': {
        'total_sessions': stats['total'] or 0, 'avg_focus': avg_focus,
        'focus_delta': round(avg_focus - (yest['af'] or 0), 1),
        'total_duration': fmt_dur(stats['total_dur'] or 0), 'total_duration_secs': stats['total_dur'] or 0,
        'avg_stress': round(stats['avg_stress'] or 0, 1), 'total_distractions': int(stats['total_dist'] or 0),
        'best_focus': round(stats['best'] or 0, 1), 'avg_cognitive_load': round(stats['avg_cli'] or 0, 1),
        'avg_cfi': round(stats['avg_cfi'] or 0, 1), 'total_blinks': int(stats['total_blinks'] or 0),
        'yesterday_sessions': yest['n'] or 0,
    }, 'trend': trend, 'distribution': distribution, 'emotion_distribution': emotion_distribution})


@analytics_bp.route('/analytics/focus-timeline', methods=['GET'])
def focus_timeline():
    uid = request.args.get('user_id', 1, type=int)
    limit = min(500, max(1, request.args.get('limit', 100, type=int)))
    conn = get_db()
    rows = conn.execute('''SELECT timestamp, focus_score, stress_level, cognitive_state,
                           cli_vision, cfi, kpm, backspace_ratio, pause_duration
                           FROM detections WHERE user_id=? ORDER BY timestamp DESC LIMIT ?''', (uid, limit)).fetchall()
    conn.close()
    timeline = []
    for row in reversed(rows):
        try: label = datetime.fromisoformat(str(row['timestamp'])).strftime('%H:%M:%S')
        except Exception: label = str(row['timestamp'])
        timeline.append({'time': label, 'focus': round(row['focus_score'] or 0, 1), 'stress': round(row['stress_level'] or 0, 1), 'state': row['cognitive_state'], 'cognitive_load': round(row['cli_vision'] or 0, 1), 'cfi': round(row['cfi'] or 0, 1), 'kpm': row['kpm'], 'backspace_ratio': row['backspace_ratio'], 'pause_duration': row['pause_duration']})
    return jsonify({'success': True, 'timeline': timeline})


@analytics_bp.route('/analytics/report.csv', methods=['GET'])
def export_report():
    uid = request.args.get('user_id', 1, type=int)
    period = request.args.get('period', 'today')
    since = _since(period).isoformat()
    conn = get_db()
    rows = conn.execute('''SELECT timestamp, session_id, face_status, data_quality, ear, blink_count,
                           blink_rate, avg_blink_duration, brow_deviation, gaze_jitter, cli_vision,
                           kpm, backspace_ratio, pause_duration, emotion, emotion_confidence,
                           state, cfi, reasons FROM cognitive_metrics
                           WHERE user_id=? AND timestamp>=? ORDER BY timestamp ASC''', (uid, since)).fetchall()
    conn.close()
    output = io.StringIO(); fields = ['timestamp','session_id','face_status','data_quality','ear','blink_count','blink_rate','avg_blink_duration','brow_deviation','gaze_jitter','cli_vision','kpm','backspace_ratio','pause_duration','emotion','emotion_confidence','state','cfi','reasons']
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for row in rows: writer.writerow(dict(row))
    content=output.getvalue(); os.makedirs(Config.EXPORT_DIR,exist_ok=True)
    with open(os.path.join(Config.EXPORT_DIR,f'cognisense_report_{uid}_{period}.csv'),'w',encoding='utf-8',newline='') as fh: fh.write(content)
    return Response(content, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=cognisense_report_{period}.csv'})


@analytics_bp.route('/analytics/alerts', methods=['GET'])
def get_alerts():
    uid = request.args.get('user_id', 1, type=int)
    conn = get_db(); rows = conn.execute('SELECT * FROM alerts WHERE user_id=? ORDER BY timestamp DESC LIMIT 50', (uid,)).fetchall(); conn.close()
    alerts = [dict(r) for r in rows]
    return jsonify({'success': True, 'alerts': alerts, 'unread_count': sum(1 for a in alerts if not a['is_read'])})


@analytics_bp.route('/analytics/alerts/mark-read', methods=['POST'])
def mark_read():
    uid = (request.get_json(silent=True) or {}).get('user_id', 1)
    conn = get_db(); conn.execute('UPDATE alerts SET is_read=1 WHERE user_id=?', (uid,)); conn.commit(); conn.close()
    return jsonify({'success': True})


@analytics_bp.route('/analytics/productivity', methods=['GET'])
def productivity():
    uid = request.args.get('user_id', 1, type=int)
    conn = get_db(); now = datetime.now(); days = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i); ds = day.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(); de = day.replace(hour=23,minute=59,second=59,microsecond=999999).isoformat()
        row = conn.execute('SELECT AVG(focus_score) af, COUNT(*) n, SUM(duration) dur FROM sessions WHERE user_id=? AND start_time>=? AND start_time<=?', (uid,ds,de)).fetchone()
        days.append({'date':day.strftime('%a %d'),'focus':round(row['af'] or 0,1),'sessions':row['n'] or 0,'study_hours':round((row['dur'] or 0)/3600,1)})
    conn.close()
    focus_scores=[d['focus'] for d in days if d['sessions']]
    avg_focus=sum(focus_scores)/len(focus_scores) if focus_scores else 0
    active_days=sum(1 for d in days if d['sessions'])
    consistency=active_days/7*100
    return jsonify({'success':True,'productivity_score':round(avg_focus*.6+consistency*.4,1),'avg_focus':round(avg_focus,1),'consistency':round(consistency,1),'active_days':active_days,'daily_data':days})
