"""Optional task triage. Receives only explicitly supplied text and numeric telemetry."""
import os
import json
import urllib.request
import urllib.error
import urllib.parse

from config import Config


def _extract_three(text):
    lines = [x.strip(' -•\t') for x in str(text).splitlines() if x.strip()]
    lines = [x for x in lines if not x.lower().startswith(('1.', '2.', '3.'))]
    return lines[:3]


def triage(task_context='', telemetry=None):
    task_context = (task_context or '').strip()
    if not task_context:
        return {'available': False, 'message': 'No task context available for triage.', 'points': []}

    provider = Config.LLM_PROVIDER
    key = Config.GROQ_API_KEY if provider == 'groq' else Config.GEMINI_API_KEY if provider == 'gemini' else ''
    if not key:
        return {'available': False, 'message': 'AI triage unavailable', 'points': []}

    telemetry = telemetry or {}
    prompt = (
        'Give exactly three short actionable points for the supplied task context. '
        'Do not mention private webcam data. Keep each point <=10 words where practical.\n'
        f'Task context:\n{task_context}\nTelemetry:\n{json.dumps(telemetry, default=str)}'
    )
    try:
        if provider == 'groq':
            body = json.dumps({
                'model': 'llama-3.1-8b-instant',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.2,
                'max_tokens': 120,
            }).encode()
            req = urllib.request.Request('https://api.groq.com/openai/v1/chat/completions', data=body, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            text = data['choices'][0]['message']['content']
        elif provider == 'gemini':
            body = json.dumps({'contents': [{'parts': [{'text': prompt}]}]}).encode()
            url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' + urllib.parse.quote(key)
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            text = data['candidates'][0]['content']['parts'][0]['text']
        else:
            return {'available': False, 'message': 'AI triage unavailable', 'points': []}
        points = _extract_three(text)
        if len(points) != 3:
            return {'available': False, 'message': 'AI triage unavailable', 'points': []}
        return {'available': True, 'message': '', 'points': points}
    except Exception as exc:
        print(f'[LLM] triage unavailable: {exc}')
        return {'available': False, 'message': 'AI triage unavailable', 'points': []}
