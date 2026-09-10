"""Persist complete session summaries and metric rows as JSON/CSV files."""
import csv
import json
import os
from datetime import datetime
from pathlib import Path

from config import Config


def _user_dir(user_id):
    path = Path(Config.SESSION_DATA_DIR) / f'user_{int(user_id)}'
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_session_files(user_id, session_row, metrics, detections=None, alerts=None):
    session_id = int(session_row['id'])
    folder = _user_dir(user_id)
    prefix = folder / f'session_{session_id}'

    payload = {
        'session': dict(session_row),
        'metrics': [dict(row) for row in metrics],
        'detections': [dict(row) for row in (detections or [])],
        'alerts': [dict(row) for row in (alerts or [])],
        'exported_at': datetime.now().isoformat(timespec='seconds'),
    }
    json_path = prefix.with_suffix('.json')
    with json_path.open('w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, default=str)

    if metrics:
        csv_path = prefix.with_suffix('.csv')
        fieldnames = sorted({key for row in metrics for key in dict(row).keys()})
        with csv_path.open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in metrics:
                writer.writerow(dict(row))

    return str(json_path), str(prefix.with_suffix('.csv')) if metrics else None
