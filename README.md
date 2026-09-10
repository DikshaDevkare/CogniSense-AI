# 🧠 CogniLast (CogniSense-AI)

> **AI-Powered Cognitive Load, Emotion Detection & Productivity Analytics Platform**

CogniLast is an intelligent full-stack system designed to detect facial micro-expressions, monitor emotional states, analyze typing patterns, and calculate real-time cognitive workload to prevent burnout and boost focus.

---

## ✨ Features & Architecture

- **🎭 Dual Face Engine:** Micro-expression tracking using both **MediaPipe Mesh** (`mediapipe_detect.js`) and **FaceAPI** (`faceapi_detect.js`).
- **🧠 Cognitive Load Engine:** Real-time mental strain calculation powered by `cognitive_engine.py` and `emotion_detector.py`.
- **⌨️ Typing Metrics Analysis:** Tracks typing behavior and rhythm (`typing_metrics.py`, `typing.py`) to detect stress.
- **⏱️ Integrated Productivity Tools:** Includes a built-in Pomodoro timer (`pomodoro.js`), task planner (`planner.html`), and session logging (`sessions.html`).
- **📊 Analytics & Triage Alerts:** Visual metrics (`analytics.html`) paired with real-time cognitive overload alerts (`alerts.html`, `triage.py`).
- **🚀 One-Click Local Execution:** Automated Windows batch scripts (`run_backend.bat`, `run_frontend.bat`) and Linux shell scripts (`run_backend.sh`).

---

## 🛠️ Tech Stack

| Component | Technologies Used |
|---|---|
| **Backend Framework** | Python 3.10+, FastAPI, SQLite (`database.py`), Uvicorn |
| **Machine Learning** | OpenCV, MediaPipe, Custom FER Emotion Model (`train_emotion_model.py`) |
| **Frontend UI** | HTML5, CSS3 (Glassmorphism), JavaScript (ES6+), Particles.js |
| **Deployment** | Vercel (`vercel.json`) |

---

## 📁 Project Directory

```text
cognilast/
├── backend/
│   ├── routes/                # API Endpoints (analytics, auth, detect, history, planner, triage, typing)
│   ├── database/              # SQLite Database connection & schemas
│   ├── fer_data/              # Facial Expression Recognition data & models
│   ├── app.py                 # Main FastAPI entry point
│   ├── cognitive_engine.py    # Cognitive load scoring algorithm
│   ├── emotion_detector.py   # Emotion detection handler
│   ├── mediapipe_engine.py   # Facial landmark processor
│   ├── typing_metrics.py     # Typing rhythm & pressure detector
│   ├── train_emotion_model.py # ML training pipeline
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── css/                   # Stylesheets (dashboard.css, login.css, main.css)
│   ├── js/                    # Client scripts (mediapipe_detect.js, faceapi_detect.js, pomodoro.js, etc.)
│   ├── pages/                 # Application views (dashboard, analytics, planner, sessions, settings, alerts)
│   └── index.html             # Landing page
├── run_backend.bat            # Windows script to launch backend
├── run_frontend.bat           # Windows script to launch frontend
├── run_backend.sh             # Linux/Mac startup script
├── vercel.json                # Vercel deployment configuration
└── README.md                  # Project documentation