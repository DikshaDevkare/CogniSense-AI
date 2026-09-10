# app.py — CogniSense AI (additive AegisMind integration)
from flask import Flask
from flask_cors import CORS
from flask import send_from_directory

from config import Config
from database import init_db
from routes.auth import auth_bp
from routes.detect import detect_bp
from routes.history import history_bp
from routes.planner import planner_bp
from routes.analytics import analytics_bp
from routes.typing import typing_bp
from routes.triage import triage_bp

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, resources={r'/api/*': {'origins': '*'}})

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(detect_bp, url_prefix='/api')
app.register_blueprint(history_bp, url_prefix='/api')
app.register_blueprint(planner_bp, url_prefix='/api')
app.register_blueprint(analytics_bp, url_prefix='/api')
app.register_blueprint(typing_bp, url_prefix='/api')
app.register_blueprint(triage_bp, url_prefix='/api')


@app.route('/api/status')
def status():
    return {'status': 'online', 'version': '1.1.0', 'model': 'CogniSense-AI+AegisMind'}


@app.route('/')
def home():
    return send_from_directory('../frontend/pages', 'dashboard.html')


if __name__ == '__main__':
    init_db()
    print('✅ CogniSense AI Backend running on http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG)
