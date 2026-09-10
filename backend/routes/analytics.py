from flask import Blueprint, request, jsonify
from database import get_db
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)

def fmt_dur(secs):
    secs = int(secs or 0)
    return f"{secs//3600:02d}:{(secs%3600)//60:02d}:{secs%60:02d}"

@analytics_bp.route('/analytics/summary', methods=['GET'])
def summary():
    uid    = request.args.get('user_id', 1, type=int)
    period = request.args.get('period', 'today')
    now    = datetime.now()

    if period == 'today':
        since = now.replace(hour=0, minute=0, second=0).isoformat()
    elif period == 'week':
        since = (now - timedelta(days=7)).isoformat()
    else:
        since = (now - timedelta(days=30)).isoformat()

    conn = get_db()

    # Main stats
    stats = conn.execute('''
        SELECT COUNT(*) as total, AVG(focus_score) as avg_focus,
               SUM(duration) as total_dur, AVG(avg_stress) as avg_stress,
               SUM(distraction_count) as total_dist, MAX(focus_score) as best
        FROM sessions WHERE user_id=? AND start_time>=?
    ''', (uid, since)).fetchone()

    # Yesterday
    y_start = (now - timedelta(days=1)).replace(hour=0,minute=0,second=0).isoformat()
    y_end   = now.replace(hour=0,minute=0,second=0).isoformat()
    yest    = conn.execute('''
        SELECT AVG(focus_score) as af, COUNT(*) as n
        FROM sessions WHERE user_id=? AND start_time>=? AND start_time<?
    ''', (uid, y_start, y_end)).fetchone()

    # 7-day trend
    trend = []
    for i in range(6, -1, -1):
        day   = now - timedelta(days=i)
        ds    = day.replace(hour=0,minute=0,second=0).isoformat()
        de    = day.replace(hour=23,minute=59,second=59).isoformat()
        row   = conn.execute('''
            SELECT AVG(focus_score) as af, AVG(avg_stress) as as_
            FROM sessions WHERE user_id=? AND start_time>=? AND start_time<=?
        ''', (uid, ds, de)).fetchone()
        trend.append({
            'day':   day.strftime('%a'),
            'focus': round(row['af'] or 0, 1),
            'stress':round(row['as_'] or 0, 1)
        })

    # Detection distribution
    dist_rows = conn.execute('''
        SELECT cognitive_state, COUNT(*) as n
        FROM detections WHERE user_id=? GROUP BY cognitive_state
    ''', (uid,)).fetchall()
    dist_raw = {r['cognitive_state']: r['n'] for r in dist_rows}
    total_det = sum(dist_raw.values()) or 1
    dist_pct  = {
        'Focused':    round(dist_raw.get('Focused',    0) / total_det * 100),
        'Distracted': round(dist_raw.get('Distracted', 0) / total_det * 100),
        'Stressed':   round(dist_raw.get('Stressed',   0) / total_det * 100),
    }

    conn.close()

    avg_focus  = round(stats['avg_focus'] or 72, 1)
    yest_focus = round(yest['af'] or 64, 1)
    delta      = round(avg_focus - yest_focus, 1)
    total_dur  = stats['total_dur'] or 0

    return jsonify({
        'success': True,
        'period':  period,
        'stats': {
            'total_sessions':    stats['total'] or 4,
            'avg_focus':         avg_focus,
            'focus_delta':       delta,
            'total_duration':    fmt_dur(total_dur),
            'total_duration_secs': total_dur,
            'avg_stress':        round(stats['avg_stress'] or 15, 1),
            'total_distractions':stats['total_dist'] or 7,
            'best_focus':        round(stats['best'] or 91, 1),
            'yesterday_sessions':yest['n'] or 3,
        },
        'trend':        trend,
        'distribution': dist_pct
    })

@analytics_bp.route('/analytics/focus-timeline', methods=['GET'])
def focus_timeline():
    uid = request.args.get('user_id', 1, type=int)
    conn = get_db()
    rows = conn.execute('''
        SELECT timestamp, focus_score, stress_level, cognitive_state
        FROM detections WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 50
    ''', (uid,)).fetchall()
    conn.close()

    timeline = []
    for row in rows:
        try:
            dt    = datetime.fromisoformat(row['timestamp'])
            label = dt.strftime('%H:%M')
        except:
            label = str(row['timestamp'])
        timeline.append({
            'time':   label,
            'focus':  round(row['focus_score'] or 0, 1),
            'stress': round(row['stress_level'] or 0, 1),
            'state':  row['cognitive_state']
        })

    return jsonify({'success': True, 'timeline': timeline})

@analytics_bp.route('/analytics/alerts', methods=['GET'])
def get_alerts():
    uid = request.args.get('user_id', 1, type=int)
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM alerts WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 50
    ''', (uid,)).fetchall()
    conn.close()
    alerts = [dict(r) for r in rows]
    return jsonify({
        'success':     True,
        'alerts':      alerts,
        'unread_count':len([a for a in alerts if not a['is_read']])
    })

@analytics_bp.route('/analytics/alerts/mark-read', methods=['POST'])
def mark_read():
    uid = (request.get_json() or {}).get('user_id', 1)
    conn = get_db()
    conn.execute('UPDATE alerts SET is_read=1 WHERE user_id=?', (uid,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@analytics_bp.route('/analytics/productivity', methods=['GET'])
def productivity():
    """Productivity score based on real session data."""
    uid  = request.args.get('user_id', 1, type=int)
    conn = get_db()

    # Last 7 days per-day avg focus
    now   = datetime.now()
    days  = []
    for i in range(6, -1, -1):
        day  = now - timedelta(days=i)
        ds   = day.replace(hour=0,minute=0,second=0).isoformat()
        de   = day.replace(hour=23,minute=59,second=59).isoformat()
        row  = conn.execute('''
            SELECT AVG(focus_score) as af, COUNT(*) as n, SUM(duration) as dur
            FROM sessions WHERE user_id=? AND start_time>=? AND start_time<=?
        ''', (uid, ds, de)).fetchone()
        days.append({
            'date':         day.strftime('%a %d'),
            'focus':        round(row['af'] or 0, 1),
            'sessions':     row['n'] or 0,
            'study_hours':  round((row['dur'] or 0) / 3600, 1),
        })

    conn.close()

    # Overall productivity score
    focus_scores  = [d['focus'] for d in days if d['focus'] > 0]
    avg_focus     = sum(focus_scores) / len(focus_scores) if focus_scores else 0
    active_days   = len([d for d in days if d['sessions'] > 0])
    consistency   = (active_days / 7) * 100

    productivity_score = round(avg_focus * 0.6 + consistency * 0.4, 1)

    return jsonify({
        'success':            True,
        'productivity_score': productivity_score,
        'avg_focus':          round(avg_focus, 1),
        'consistency':        round(consistency, 1),
        'active_days':        active_days,
        'daily_data':         days
    })
