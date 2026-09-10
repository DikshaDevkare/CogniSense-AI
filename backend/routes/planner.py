# routes/planner.py
from flask import Blueprint, request, jsonify
from database import get_db
from datetime import date

planner_bp = Blueprint('planner', __name__)

@planner_bp.route('/planner', methods=['GET'])
def get_planner():
    user_id = request.args.get('user_id', 1, type=int)
    plan_date = request.args.get('date', date.today().isoformat())

    conn = get_db()
    rows = conn.execute('''
        SELECT id, subject, start_time, end_time, date, completed
        FROM planner
        WHERE user_id = ? AND date = ?
        ORDER BY start_time ASC
    ''', (user_id, plan_date)).fetchall()
    conn.close()

    if not rows:
        # Return default plan for demo
        return jsonify({
            'success': True,
            'date': plan_date,
            'sessions': [
                {'id': 1, 'subject': 'Data Structures', 'start_time': '09:00', 'end_time': '10:30', 'completed': True},
                {'id': 2, 'subject': 'Machine Learning', 'start_time': '11:00', 'end_time': '12:30', 'completed': True},
                {'id': 3, 'subject': 'Database Systems', 'start_time': '14:00', 'end_time': '15:30', 'completed': False},
                {'id': 4, 'subject': 'Operating Systems', 'start_time': '16:00', 'end_time': '17:30', 'completed': False},
            ],
            'recommendations': get_ai_recommendations(user_id)
        })

    return jsonify({
        'success': True,
        'date': plan_date,
        'sessions': [dict(r) for r in rows],
        'recommendations': get_ai_recommendations(user_id)
    })


@planner_bp.route('/planner', methods=['POST'])
def add_planner_session():
    data = request.get_json() or {}
    user_id = data.get('user_id', 1)
    subject = data.get('subject', '').strip()
    start_time = data.get('start_time', '09:00')
    end_time = data.get('end_time', '10:00')
    plan_date = data.get('date', date.today().isoformat())

    if not subject:
        return jsonify({'success': False, 'message': 'Subject is required'}), 400

    conn = get_db()
    cur = conn.execute('''
        INSERT INTO planner (user_id, subject, start_time, end_time, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, subject, start_time, end_time, plan_date))
    item_id = cur.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': item_id, 'subject': subject})


@planner_bp.route('/planner/<int:item_id>/complete', methods=['PATCH'])
def toggle_complete(item_id):
    data = request.get_json() or {}
    completed = data.get('completed', True)

    conn = get_db()
    conn.execute('UPDATE planner SET completed = ? WHERE id = ?', (int(completed), item_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'completed': completed})


@planner_bp.route('/planner/<int:item_id>', methods=['DELETE'])
def delete_planner_item(item_id):
    conn = get_db()
    conn.execute('DELETE FROM planner WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


def get_ai_recommendations(user_id):
    """Generate AI-driven study recommendations based on session history."""
    conn = get_db()
    recent = conn.execute('''
        SELECT AVG(focus_score) as avg_focus,
               AVG(avg_stress) as avg_stress,
               MAX(duration) as max_dur
        FROM sessions WHERE user_id = ?
        ORDER BY start_time DESC LIMIT 5
    ''', (user_id,)).fetchone()
    conn.close()

    recs = []
    avg_focus = recent['avg_focus'] or 72
    avg_stress = recent['avg_stress'] or 20

    recs.append({'icon': '🌅', 'text': 'You are most productive in the morning.'})

    if avg_stress > 40:
        recs.append({'icon': '☕', 'text': 'Take a 10 min break. Your focus is dropping.'})
        recs.append({'icon': '🧘', 'text': 'Practice deep breathing before your next session.'})
    else:
        recs.append({'icon': '⏱️', 'text': 'Try Pomodoro technique for better focus.'})

    if avg_focus < 65:
        recs.append({'icon': '🎯', 'text': 'Schedule difficult topics early when focus is highest.'})
    else:
        recs.append({'icon': '🏆', 'text': 'Great focus streak! Keep your current routine.'})

    return recs