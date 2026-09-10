from flask import Blueprint, request, jsonify
from llm_triage import triage

triage_bp = Blueprint('triage', __name__)


@triage_bp.route('/triage', methods=['POST'])
def task_triage():
    data = request.get_json(silent=True) or {}
    context = data.get('task_context', '')
    telemetry = data.get('telemetry', {})
    return jsonify({'success': True, 'data': triage(context, telemetry)})
