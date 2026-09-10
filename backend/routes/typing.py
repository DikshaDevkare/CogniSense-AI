from flask import Blueprint, request, jsonify
from typing_metrics import get_typing_metrics, reset_typing_metrics

typing_bp = Blueprint('typing', __name__)


@typing_bp.route('/typing', methods=['POST'])
def typing_event():
    data = request.get_json(silent=True) or {}
    uid = int(data.get('user_id', 1))
    tracker = get_typing_metrics(uid)
    metrics = tracker.record(
        key_count=data.get('keypress_count', 0),
        backspace_count=data.get('backspace_count', 0),
        timestamp=data.get('timestamp')
    )
    return jsonify({'success': True, 'data': metrics})


@typing_bp.route('/typing', methods=['GET'])
def typing_snapshot():
    uid = request.args.get('user_id', 1, type=int)
    return jsonify({'success': True, 'data': get_typing_metrics(uid).snapshot()})


@typing_bp.route('/typing/reset', methods=['POST'])
def typing_reset():
    uid = int((request.get_json(silent=True) or {}).get('user_id', 1))
    reset_typing_metrics(uid)
    return jsonify({'success': True})
