// ============================================================
// pomodoro.js — Smart Break Timer
// 25 min study → 5 min break auto popup
// ============================================================

const POMODORO_STUDY_MINS = 25;
const POMODORO_BREAK_MINS = 5;

let pomodoroTimer    = null;
let pomodoroSeconds  = POMODORO_STUDY_MINS * 60;
let pomodoroMode     = 'study';   // 'study' | 'break'
let pomodoroRunning  = false;
let pomodoroCount    = 0;

// ── Create Pomodoro UI ────────────────────────────────────
function initPomodoro() {
  // Only inject on dashboard
  if (!document.getElementById('webcam-feed')) return;

  const html = `
  <div id="pomodoro-widget" style="
    position:fixed; bottom:24px; left:calc(220px + 24px); z-index:999;
    background:rgba(10,10,26,0.95); border:1px solid rgba(168,85,247,0.35);
    border-radius:16px; padding:16px 20px; min-width:220px;
    backdrop-filter:blur(16px); box-shadow:0 8px 32px rgba(0,0,0,0.4);
    font-family:'Exo 2',sans-serif;">

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <span style="font-family:'Orbitron',monospace;font-size:11px;font-weight:700;
        color:#a855f7;letter-spacing:1px">⏱ POMODORO</span>
      <span id="pomo-count" style="font-size:11px;color:#475569">0 sessions</span>
    </div>

    <div style="text-align:center;margin-bottom:12px">
      <div id="pomo-mode" style="font-size:12px;font-weight:600;color:#94a3b8;
        text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">Study Time</div>
      <div id="pomo-time" style="font-family:'Orbitron',monospace;font-size:28px;
        font-weight:700;color:#f1f5f9">25:00</div>
    </div>

    <div style="height:4px;background:rgba(255,255,255,0.08);border-radius:2px;margin-bottom:12px">
      <div id="pomo-bar" style="height:100%;width:100%;border-radius:2px;
        background:linear-gradient(90deg,#a855f7,#6366f1);transition:width 1s linear"></div>
    </div>

    <div style="display:flex;gap:8px">
      <button id="pomo-btn" onclick="togglePomodoro()" style="
        flex:1;padding:8px;background:linear-gradient(135deg,#a855f7,#6366f1);
        border:none;border-radius:8px;color:white;font-weight:600;font-size:12px;
        cursor:pointer;font-family:'Exo 2',sans-serif;">Start</button>
      <button onclick="resetPomodoro()" style="
        padding:8px 12px;background:rgba(255,255,255,0.06);
        border:1px solid rgba(168,85,247,0.2);border-radius:8px;color:#94a3b8;
        font-size:12px;cursor:pointer;font-family:'Exo 2',sans-serif;">Reset</button>
    </div>
  </div>

  <!-- Break Alert Modal -->
  <div id="break-modal" style="
    display:none;position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);
    align-items:center;justify-content:center;">
    <div style="
      background:rgba(10,10,26,0.98);border:1px solid rgba(168,85,247,0.4);
      border-radius:24px;padding:40px;max-width:420px;text-align:center;
      box-shadow:0 20px 60px rgba(168,85,247,0.3);">
      <div style="font-size:48px;margin-bottom:16px" id="modal-icon">☕</div>
      <h2 id="modal-title" style="font-family:'Orbitron',monospace;font-size:22px;
        color:#f1f5f9;margin-bottom:8px">Break Time!</h2>
      <p id="modal-msg" style="color:#94a3b8;font-size:14px;margin-bottom:24px;line-height:1.6">
        You've studied for 25 minutes. Take a 5-minute break to maintain focus!
      </p>
      <div style="display:flex;gap:12px;justify-content:center">
        <button onclick="startBreak()" style="
          padding:12px 28px;background:linear-gradient(135deg,#a855f7,#6366f1);
          border:none;border-radius:12px;color:white;font-weight:700;font-size:14px;
          cursor:pointer;font-family:'Exo 2',sans-serif;
          box-shadow:0 4px 20px rgba(168,85,247,0.4)">Start Break</button>
        <button onclick="skipBreak()" style="
          padding:12px 28px;background:rgba(255,255,255,0.06);
          border:1px solid rgba(168,85,247,0.3);border-radius:12px;
          color:#94a3b8;font-size:14px;cursor:pointer;font-family:'Exo 2',sans-serif">
          Skip Break</button>
      </div>
    </div>
  </div>`;

  document.body.insertAdjacentHTML('beforeend', html);
}

// ── Timer logic ───────────────────────────────────────────
function togglePomodoro() {
  if (pomodoroRunning) {
    pausePomodoro();
  } else {
    startPomodoro();
  }
}

function startPomodoro() {
  pomodoroRunning = true;
  document.getElementById('pomo-btn').textContent = 'Pause';

  pomodoroTimer = setInterval(() => {
    pomodoroSeconds--;
    updatePomodoroUI();

    if (pomodoroSeconds <= 0) {
      clearInterval(pomodoroTimer);
      pomodoroRunning = false;

      if (pomodoroMode === 'study') {
        pomodoroCount++;
        showBreakModal();
      } else {
        showStudyModal();
        pomodoroMode    = 'study';
        pomodoroSeconds = POMODORO_STUDY_MINS * 60;
        updatePomodoroUI();
      }
    }
  }, 1000);
}

function pausePomodoro() {
  clearInterval(pomodoroTimer);
  pomodoroRunning = false;
  document.getElementById('pomo-btn').textContent = 'Resume';
}

function resetPomodoro() {
  clearInterval(pomodoroTimer);
  pomodoroRunning  = false;
  pomodoroMode     = 'study';
  pomodoroSeconds  = POMODORO_STUDY_MINS * 60;
  updatePomodoroUI();
  const btn = document.getElementById('pomo-btn');
  if (btn) btn.textContent = 'Start';
}

function startBreak() {
  document.getElementById('break-modal').style.display = 'none';
  pomodoroMode    = 'break';
  pomodoroSeconds = POMODORO_BREAK_MINS * 60;
  updatePomodoroUI();
  document.getElementById('pomo-btn').textContent = 'Pause';
  startPomodoro();
}

function skipBreak() {
  document.getElementById('break-modal').style.display = 'none';
  pomodoroMode    = 'study';
  pomodoroSeconds = POMODORO_STUDY_MINS * 60;
  updatePomodoroUI();
  document.getElementById('pomo-btn').textContent = 'Start';
}

function showBreakModal() {
  const m = document.getElementById('break-modal');
  document.getElementById('modal-icon').textContent  = '☕';
  document.getElementById('modal-title').textContent = 'Break Time!';
  document.getElementById('modal-msg').textContent   =
    `Great job! You've completed ${pomodoroCount} pomodoro session${pomodoroCount>1?'s':''}. Take a 5-minute break!`;
  m.style.display = 'flex';

  // Play notification sound
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.8);
    osc.start(); osc.stop(ctx.currentTime + 0.8);
  } catch {}

  document.getElementById('pomo-count').textContent = `${pomodoroCount} sessions`;
}

function showStudyModal() {
  const m = document.getElementById('break-modal');
  document.getElementById('modal-icon').textContent  = '🎯';
  document.getElementById('modal-title').textContent = 'Break Over!';
  document.getElementById('modal-msg').textContent   = 'Time to focus again! Start your next study session.';
  m.style.display = 'flex';
}

function updatePomodoroUI() {
  const mins  = Math.floor(pomodoroSeconds / 60);
  const secs  = pomodoroSeconds % 60;
  const total = pomodoroMode === 'study'
    ? POMODORO_STUDY_MINS * 60
    : POMODORO_BREAK_MINS * 60;
  const pct   = (pomodoroSeconds / total) * 100;

  const timeEl = document.getElementById('pomo-time');
  const barEl  = document.getElementById('pomo-bar');
  const modeEl = document.getElementById('pomo-mode');

  if (timeEl) timeEl.textContent = `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
  if (barEl)  barEl.style.width  = `${pct}%`;
  if (modeEl) {
    modeEl.textContent = pomodoroMode === 'study' ? 'Study Time' : 'Break Time';
    modeEl.style.color = pomodoroMode === 'study' ? '#a855f7' : '#22c55e';
  }

  // Color shift when time low
  if (timeEl && pomodoroSeconds <= 60) {
    timeEl.style.color = '#ef4444';
  } else if (timeEl) {
    timeEl.style.color = '#f1f5f9';
  }
}

// Init on page load
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(initPomodoro, 500);
});