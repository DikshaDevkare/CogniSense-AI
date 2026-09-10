from flask import Blueprint, request, jsonify
from database import get_db
from datetime import date

planner_bp = Blueprint('planner', __name__)


@planner_bp.route('/planner', methods=['GET'])
def get_planner():
    user_id = request.args.get('user_id', 1, type=int)
    plan_date = request.args.get('date', date.today().isoformat())
    conn = get_db()
    rows = conn.execute('''SELECT id, subject, start_time, end_time, date, completed
                           FROM planner WHERE user_id=? AND date=? ORDER BY start_time ASC''', (user_id, plan_date)).fetchall()
    conn.close()
    return jsonify({'success': True, 'date': plan_date, 'sessions': [dict(r) for r in rows], 'recommendations': get_ai_recommendations(user_id)})


@planner_bp.route('/planner', methods=['POST'])
def add_planner_session():
    data = request.get_json(silent=True) or {}
    user_id = int(data.get('user_id', 1)); subject = str(data.get('subject', '')).strip()
    start_time = data.get('start_time', '09:00'); end_time = data.get('end_time', '10:00'); plan_date = data.get('date', date.today().isoformat())
    if not subject: return jsonify({'success': False, 'message': 'Subject is required'}), 400
    conn = get_db(); cur = conn.execute('INSERT INTO planner (user_id,subject,start_time,end_time,date) VALUES (?,?,?,?,?)', (user_id,subject,start_time,end_time,plan_date)); item_id=cur.lastrowid; conn.commit(); conn.close()
    return jsonify({'success': True, 'id': item_id, 'subject': subject})


@planner_bp.route('/planner/<int:item_id>/complete', methods=['PATCH'])
def toggle_complete(item_id):
    data = request.get_json(silent=True) or {}; completed = bool(data.get('completed', True))
    conn=get_db(); conn.execute('UPDATE planner SET completed=? WHERE id=?',(int(completed),item_id)); conn.commit(); conn.close()
    return jsonify({'success': True, 'completed': completed})


@planner_bp.route('/planner/<int:item_id>', methods=['DELETE'])
def delete_planner_item(item_id):
    conn=get_db(); conn.execute('DELETE FROM planner WHERE id=?',(item_id,)); conn.commit(); conn.close(); return jsonify({'success': True})


def get_ai_recommendations(user_id):
    conn = get_db()
    rows = conn.execute('''SELECT start_time, AVG(focus_score) focus, AVG(avg_stress) stress, AVG(avg_cognitive_load) cli,
                           AVG(duration) duration FROM sessions WHERE user_id=? GROUP BY start_time''', (user_id,)).fetchall()
    recent = conn.execute('''SELECT AVG(focus_score) focus, AVG(avg_stress) stress, AVG(avg_cognitive_load) cli,
                             AVG(duration) duration FROM sessions WHERE user_id=?''', (user_id,)).fetchone()
    conn.close()
    if not recent or recent['focus'] is None:
        return [{'icon':'📊','text':'Run a study session to unlock personalized recommendations.'}]

    recs=[]
    avg_focus=float(recent['focus'] or 0); avg_stress=float(recent['stress'] or 0); avg_cli=float(recent['cli'] or 0)
    if avg_stress > 40 or avg_cli > 65:
        recs.append({'icon':'☕','text':'Use a short break after high-strain sessions.'})
    else:
        recs.append({'icon':'⏱️','text':'Keep your current session rhythm and review results weekly.'})

    # Find strongest hour from real session start timestamps.
    hourly={}
    for row in rows:
        try:
            hour=int(str(row['start_time']).split('T')[-1].split(':')[0])
        except Exception:
            continue
        hourly.setdefault(hour, []).append(float(row['focus'] or 0))
    if hourly:
        best_hour=max(hourly, key=lambda h: sum(hourly[h])/len(hourly[h]))
        recs.append({'icon':'🌅','text':f'Your recorded focus is strongest around {best_hour:02d}:00.'})
    else:
        recs.append({'icon':'📈','text':'More sessions are needed to learn your best study time.'})

    if avg_focus < 65:
        recs.append({'icon':'🎯','text':'Schedule difficult topics during your highest-focus period.'})
    else:
        recs.append({'icon':'🏆','text':'Your recorded focus is strong; maintain the routine.'})
    return recs[:4]
