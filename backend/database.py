# database.py — SQLite setup
import sqlite3
import os
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(Config.DATABASE), exist_ok=True)
    conn = get_db()
    cur = conn.cursor()

    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            duration INTEGER DEFAULT 0,
            focus_score REAL DEFAULT 0,
            avg_stress REAL DEFAULT 0,
            distraction_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Focused',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            focus_score REAL,
            stress_level REAL,
            blink_rate REAL,
            head_movement TEXT,
            eye_consistency REAL,
            attention_score REAL,
            cognitive_state TEXT,
            fake_detected INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            alert_type TEXT,
            message TEXT,
            severity TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS planner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            date TEXT,
            completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        INSERT OR IGNORE INTO users (username, password) VALUES ('Shrushti', 'password123');
        INSERT OR IGNORE INTO users (username, password) VALUES ('admin', 'admin123');
    ''')

    conn.commit()
    conn.close()
    print("✅ Database initialized.")