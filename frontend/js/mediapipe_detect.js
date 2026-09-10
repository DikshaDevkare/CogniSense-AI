const API_URL = 'http://localhost:5000/api';

// ── Landmark indices ──────────────────────────────────────
const L_EAR = [362,385,387,263,373,380];
const R_EAR = [33, 160,158,133,153,144];
const NOSE  = 1, CHIN = 152, L_EYE = 33, R_EYE = 263;
const L_IRIS = [474,475,476,477], R_IRIS = [469,470,471,472];

// ── State ────────────────────────────────────────────────
let faceMesh = null;
let mpCamera = null;

// Blink state
let isBlinking = false, blinkStart = 0;
let blinksInWindow = 0, totalBlinks = 0;
const blinkTimestamps = [];

// Window accumulators
let windowStart      = Date.now();
let frameCount       = 0;
let faceFrames       = 0;
let earValues        = [];
let headYaws         = [];
let headPitches      = [];
let attentionScores  = [];
let lookingFwdCount  = 0;
let windowNumber     = 0;

// Session
let sessionStart     = Date.now();
let lastResult       = null;

// Focus chart data
let focusData   = [];
let focusLabels = [];

// ── EAR Calculation ──────────────────────────────────────
function calcEAR(lm, pts) {
  const p = pts.map(i => ({ x: lm[i].x, y: lm[i].y }));
  const A = dist(p[1], p[5]);
  const B = dist(p[2], p[4]);
  const C = dist(p[0], p[3]);
  return (A + B) / (2.0 * C + 1e-6);
}

function dist(a, b) {
  return Math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2);
}

// ── Head Angles ───────────────────────────────────────────
function calcHeadAngles(lm) {
  const nosex  = lm[NOSE].x;
  const leyex  = lm[L_EYE].x;
  const reyex  = lm[R_EYE].x;
  const faceCx = (leyex + reyex) / 2;
  const yaw    = (nosex - faceCx) * 160;

  const nosey  = lm[NOSE].y;
  const forey  = lm[10].y;
  const chiny  = lm[CHIN].y;
  const span   = Math.abs(chiny - forey) + 1e-6;
  const pitch  = ((nosey - forey) / span - 0.5) * 80;

  return { yaw: Math.round(yaw*10)/10, pitch: Math.round(pitch*10)/10 };
}

// ── Gaze Ratio ────────────────────────────────────────────
function calcGaze(lm) {
  try {
    const lIrisx  = L_IRIS.reduce((s,i) => s + lm[i].x, 0) / 4;
    const lLeftx  = lm[362].x, lRightx = lm[263].x;
    const lRatio  = (lIrisx - lLeftx) / (Math.abs(lRightx - lLeftx) + 1e-4);

    const rIrisx  = R_IRIS.reduce((s,i) => s + lm[i].x, 0) / 4;
    const rLeftx  = lm[33].x, rRightx = lm[133].x;
    const rRatio  = (rIrisx - rLeftx) / (Math.abs(rRightx - rLeftx) + 1e-4);

    const avg = (lRatio + rRatio) / 2;
    return { lookingFwd: avg >= 0.25 && avg <= 0.75, ratio: avg };
  } catch { return { lookingFwd: true, ratio: 0.5 }; }
}

// ── Blink Detection ───────────────────────────────────────
const EAR_THRESH    = 0.21;
const BLINK_MIN_MS  = 50;
const BLINK_MAX_MS  = 400;

function updateBlink(ear) {
  const now = Date.now();
  if (ear < EAR_THRESH) {
    if (!isBlinking) { isBlinking = true; blinkStart = now; }
  } else {
    if (isBlinking) {
      const dur = now - blinkStart;
      if (dur >= BLINK_MIN_MS && dur <= BLINK_MAX_MS) {
        blinksInWindow++;
        totalBlinks++;
        blinkTimestamps.push(now);
      }
      isBlinking = false;
    }
  }
  // keep only last 60 seconds
  const cutoff = now - 60000;
  while (blinkTimestamps.length && blinkTimestamps[0] < cutoff)
    blinkTimestamps.shift();
}

function blinkRatePerMin() {
  const now = Date.now();
  const elapsed = Math.min(60, (now - sessionStart) / 1000);
  if (elapsed < 3) return 0;
  return Math.round(blinkTimestamps.length / elapsed * 60 * 10) / 10;
}

// ── 5-Second Window Analysis ─────────────────────────────
const WINDOW_MS = 5000;

function checkWindow() {
  const elapsed = Date.now() - windowStart;
  if (elapsed < WINDOW_MS) return null;

  const n = Math.max(frameCount, 1);
  const nFace = faceFrames;
  const faceRatio = nFace / n;

  // Head stability
  let headStab = 50;
  if (headYaws.length > 3) {
    const yawStd   = std(headYaws);
    const pitchStd = std(headPitches);
    headStab = Math.max(0, Math.min(100, 100 - (yawStd + pitchStd) * 3));
  }

  // Avg attention
  const avgAttn = attentionScores.length
    ? attentionScores.reduce((a,b)=>a+b,0) / attentionScores.length
    : 0;

  // EAR consistency
  let eyeConsistency = 60;
  if (earValues.length > 5) {
    const earStd = std(earValues);
    if (earStd >= 0.008 && earStd <= 0.08)
      eyeConsistency = Math.min(100, 50 + earStd * 600);
    else if (earStd < 0.008)
      eyeConsistency = 20;
    else
      eyeConsistency = Math.max(10, 80 - earStd * 300);
  }

  // Blink rate
  const br = blinkRatePerMin();

  // ── SCORING ──
  let focus = 0, stress = 0, distract = 0;

  // Attention (30)
  if (avgAttn >= 80)      { focus += 30; }
  else if (avgAttn >= 60) { focus += 20; distract += 5; }
  else if (avgAttn >= 40) { focus += 10; distract += 15; }
  else                    { distract += 25; }

  // Head stability (20)
  if (headStab >= 80)      { focus += 20; }
  else if (headStab >= 55) { focus += 12; distract += 5; }
  else                     { distract += 18; stress += 5; }

  // Blink rate (20) — normal 10-20/min
  if (br >= 10 && br <= 20)  { focus += 20; }
  else if (br > 28)          { stress += 22; distract += 5; }
  else if (br > 22)          { stress += 12; focus += 5; }
  else if (br < 6 && br > 0) { focus += 15; stress += 5; }
  else if (br === 0)         { distract += 10; } // no blink = face not detected

  // Eye consistency (15)
  if (eyeConsistency >= 75)      { focus += 15; }
  else if (eyeConsistency >= 50) { focus += 8; distract += 5; }
  else                           { distract += 12; }

  // Face presence (15)
  if (faceRatio >= 0.85)      { focus += 15; }
  else if (faceRatio >= 0.5)  { focus += 7; distract += 7; }
  else                        { distract += 15; }

  // Normalize
  const total = Math.max(focus + stress + distract, 1);
  const focusPct   = Math.min(100, Math.round(focus   / total * 100));
  const stressPct  = Math.min(100, Math.round(stress  / total * 100));
  const distractPct = Math.min(100, Math.round(distract / total * 100));

  // State
  let state = 'Focused';
  if (focusPct < 55 && stressPct >= 38)   state = 'Stressed';
  else if (focusPct < 55)                  state = 'Distracted';

  // Fake detection
  const fakeDetected = eyeConsistency < 20 && br < 2 && faceRatio > 0.9;

  const result = {
    state, focusPct, stressPct, distractPct,
    blinkRate: br, headStab: Math.round(headStab),
    eyeConsistency: Math.round(eyeConsistency),
    avgAttn: Math.round(avgAttn),
    faceRatio: Math.round(faceRatio * 100),
    fakeDetected,
    windowNumber: windowNumber++,
  };

  // Reset window
  windowStart     = Date.now();
  frameCount      = 0;
  faceFrames      = 0;
  blinksInWindow  = 0;
  earValues       = [];
  headYaws        = [];
  headPitches     = [];
  attentionScores = [];
  lookingFwdCount = 0;

  return result;
}

function std(arr) {
  if (arr.length < 2) return 0;
  const mean = arr.reduce((a,b)=>a+b,0) / arr.length;
  return Math.sqrt(arr.reduce((s,v)=>s+(v-mean)**2,0)/arr.length);
}

// ── Draw face landmarks on canvas ────────────────────────
function drawLandmarks(canvas, video, landmarks) {
  canvas.width  = video.videoWidth  || video.offsetWidth;
  canvas.height = video.videoHeight || video.offsetHeight;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!landmarks) return;

  const w = canvas.width, h = canvas.height;

  // Draw key eye landmarks
  const eyePts = [...L_EAR, ...R_EAR];
  ctx.fillStyle = 'rgba(168,85,247,0.8)';
  eyePts.forEach(i => {
    ctx.beginPath();
    ctx.arc(landmarks[i].x * w, landmarks[i].y * h, 2, 0, Math.PI*2);
    ctx.fill();
  });

  // Draw nose
  ctx.fillStyle = 'rgba(6,182,212,0.9)';
  ctx.beginPath();
  ctx.arc(landmarks[NOSE].x * w, landmarks[NOSE].y * h, 3, 0, Math.PI*2);
  ctx.fill();

  // Face outline (simplified)
  const outlinePts = [10,338,297,332,284,251,389,356,454,323,361,288,
                      397,365,379,378,400,377,152,148,176,149,150,136,
                      172,58,132,93,234,127,162,21,54,103,67,109,10];
  ctx.strokeStyle = 'rgba(168,85,247,0.3)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  outlinePts.forEach((i, idx) => {
    const x = landmarks[i].x * w;
    const y = landmarks[i].y * h;
    idx === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  });
  ctx.stroke();
}

// ── Update Dashboard UI ───────────────────────────────────
function updateUI(result, live) {
  if (!result) return;

  const { state, focusPct, stressPct, distractPct,
          blinkRate, headStab, eyeConsistency, avgAttn,
          faceRatio, fakeDetected } = result;

  // Ring
  const ring = document.getElementById('cognitive-ring');
  const pctEl = document.getElementById('ring-pct');
  const stateEl = document.getElementById('ring-state');
  const msgEl = document.getElementById('ring-msg');

  if (ring) {
    const circumference = 339.3;
    ring.style.strokeDashoffset = circumference - (focusPct/100)*circumference;
    const colors = { Focused:'#22c55e', Distracted:'#eab308', Stressed:'#ef4444' };
    ring.style.stroke = colors[state] || '#a855f7';
  }
  if (pctEl)   pctEl.textContent   = `${focusPct}%`;
  if (stateEl) { stateEl.textContent = state; stateEl.style.color = ({Focused:'#22c55e',Distracted:'#eab308',Stressed:'#ef4444'})[state]; }
  if (msgEl)   { msgEl.textContent = ({Focused:'Great focus! 🎯',Distracted:'Try to refocus 👀',Stressed:'Deep breath 🧘'})[state] || ''; }

  // Metric cards
  setText('metric-focus',       `${focusPct}%`);
  setText('metric-distraction', `${distractPct}%`);
  setText('metric-stress',      `${stressPct}%`);
  setText('metric-blink',       blinkRate > 0 ? `${blinkRate}/min` : '--');
  setText('qs-focus',           `${focusPct}%`);
  setText('live-blink-count',   blinksInWindow);
  setText('total-blink-count',  totalBlinks);

  // Stress badge
  const qst = document.getElementById('qs-stress');
  if (qst) {
    const lvl = stressPct > 60 ? 'High' : stressPct > 30 ? 'Medium' : 'Low';
    qst.innerHTML = `<span class="badge badge-${lvl==='High'?'stressed':lvl==='Medium'?'distracted':'focused'}">${lvl}</span>`;
  }

  // Biometric bars
  setBar('bar-attention', avgAttn,         '#a855f7,#6366f1');
  setBar('bar-head',      headStab,        '#22c55e,#0ea5e9');
  setBar('bar-eye',       eyeConsistency,  '#06b6d4,#0ea5e9');
  setBar('bar-gaze',      live.lookingFwd ? 90 : 20, '#eab308,#f97316');

  setText('label-attention', `${avgAttn}%`);
  setText('label-head',      headStab >= 70 ? 'Stable' : 'Moving');
  setText('label-eye',       `${eyeConsistency}%`);
  setText('label-looking',   live.lookingFwd ? 'Forward ✓' : 'Away ✗');

  // Emotion badge
  const emoBadge = document.getElementById('emotion-badge');
  if (emoBadge) {
    const icons = {Focused:'🎯',Distracted:'😕',Stressed:'😰'};
    emoBadge.textContent = `${icons[state]||'🧠'} ${state}`;
    const ecols = {Focused:'rgba(34,197,94,0.15)',Distracted:'rgba(234,179,8,0.15)',Stressed:'rgba(239,68,68,0.15)'};
    emoBadge.style.background = ecols[state] || 'rgba(168,85,247,0.15)';
  }

  // Focus chart
  if (focusData.length >= 20) { focusData.shift(); focusLabels.shift(); }
  focusData.push(focusPct);
  const now = new Date();
  focusLabels.push(`${now.getHours()}:${now.getMinutes().toString().padStart(2,'0')}`);
  if (window.focusChartObj) {
    window.focusChartObj.data.labels = focusLabels;
    window.focusChartObj.data.datasets[0].data = focusData;
    window.focusChartObj.update('none');
  }

  // Alert
  const container = document.getElementById('live-alerts');
  if (container) {
    let msg = null, type = 'info', icon = '💡';
    if (fakeDetected)             { msg='⚠️ Unnatural behavior detected';      type='warning'; icon='⚠️'; }
    else if (state==='Stressed')  { msg='😰 High stress detected!';             type='danger';  icon='🚨'; }
    else if (state==='Distracted'){ msg='👀 Distraction detected — refocus!';   type='warning'; icon='⚠️'; }
    else if (!live.lookingFwd)    { msg='👁️ Looking away from screen';           type='info';    icon='👁️'; }

    if (msg) {
      const item = document.createElement('div');
      item.className = `alert-item ${type}`;
      item.innerHTML = `<div class="alert-icon">${icon}</div>
        <div class="alert-text"><p>${msg}</p><span>Just now</span></div>`;
      item.style.animation = 'fadeInUp 0.4s ease';
      container.prepend(item);
      while (container.children.length > 5) container.lastElementChild.remove();
    }
  }

  // Save to backend
  saveToBackend(result);
}

// ── Save results to Flask backend ────────────────────────
async function saveToBackend(result) {
  try {
    await fetch(`${API_URL}/detect`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        user_id:    (window.currentUser||{id:1}).id,
        state:      result.state,
        focus:      result.focusPct,
        stress:     result.stressPct,
        blink_rate: result.blinkRate,
        attention:  result.avgAttn,
        no_frame:   true,  // tell backend we already have result
      })
    });
  } catch {}
}

// ── Helpers ───────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id); if(el) el.textContent = val;
}
function setBar(id, pct, gradient) {
  const el = document.getElementById(id);
  if(el){ el.style.width=`${Math.max(0,Math.min(100,Math.round(pct)))}%`; el.style.background=`linear-gradient(90deg,${gradient})`; }
}

// ── MediaPipe onResults callback ─────────────────────────
function onFaceResults(results) {
  const video  = document.getElementById('webcam-feed');
  const lmCanvas = document.getElementById('landmark-canvas');
  const faceBadge = document.getElementById('face-status-badge');
  const obsBar    = document.getElementById('obs-progress-bar');
  const obsLabel  = document.getElementById('obs-timer-label');
  const obsBadge  = document.getElementById('obs-status-badge');

  frameCount++;
  const elapsed = Date.now() - windowStart;
  const progress = Math.min(100, Math.round(elapsed / WINDOW_MS * 100));

  if (obsBar)   obsBar.style.width = `${progress}%`;
  if (obsBadge) {
    const secsLeft = Math.max(0, ((WINDOW_MS - elapsed)/1000).toFixed(1));
    obsBadge.textContent = progress < 100 ? `⏱ ${secsLeft}s` : '✓';
  }

  if (!results.multiFaceLandmarks || results.multiFaceLandmarks.length === 0) {
    // No face
    drawLandmarks(lmCanvas, video, null);
    if (faceBadge) { faceBadge.textContent='No Face'; faceBadge.style.background='rgba(239,68,68,0.2)'; faceBadge.style.color='#ef4444'; }
    if (obsLabel)  obsLabel.textContent = 'No face detected — look at camera';
    if (obsLabel)  obsLabel.style.color = '#ef4444';

    const win = checkWindow();
    if (win) updateUI(win, { lookingFwd: false });
    return;
  }

  // Face detected!
  const lm = results.multiFaceLandmarks[0];
  faceFrames++;

  if (faceBadge) { faceBadge.textContent='Face ✓'; faceBadge.style.background='rgba(34,197,94,0.2)'; faceBadge.style.color='#22c55e'; }
  if (obsLabel)  { obsLabel.textContent = `Observing... ${Math.max(0,((WINDOW_MS-elapsed)/1000).toFixed(1))}s`; obsLabel.style.color='var(--cyan)'; }

  // Draw landmarks
  drawLandmarks(lmCanvas, video, lm);

  // EAR
  const lEAR  = calcEAR(lm, L_EAR);
  const rEAR  = calcEAR(lm, R_EAR);
  const avgEAR = (lEAR + rEAR) / 2;
  earValues.push(avgEAR);
  updateBlink(avgEAR);
  setText('live-blink-count', blinksInWindow);
  setText('total-blink-count', totalBlinks);

  // Head angles
  const { yaw, pitch } = calcHeadAngles(lm);
  headYaws.push(yaw);
  headPitches.push(pitch);

  // Gaze
  const { lookingFwd, ratio } = calcGaze(lm);
  if (lookingFwd) lookingFwdCount++;

  // Per-frame attention
  let attn = 0;
  if (lookingFwd)        attn += 35;
  if (Math.abs(yaw) < 15)  attn += 25;
  if (Math.abs(pitch) < 12) attn += 20;
  if (avgEAR > EAR_THRESH)  attn += 10;
  if (Math.abs(yaw) < 8)   attn += 10;
  attentionScores.push(attn);

  // Check 5-second window
  const win = checkWindow();
  if (win) {
    if (obsLabel) { obsLabel.textContent='Analysis complete ✓'; obsLabel.style.color='var(--green)'; }
    updateUI(win, { lookingFwd });
  }
}

// ── Init MediaPipe FaceMesh ───────────────────────────────
async function initMediaPipe() {
  const video = document.getElementById('webcam-feed');
  if (!video) return;

  try {
    // Check if MediaPipe loaded
    if (typeof FaceMesh === 'undefined') {
      console.error('MediaPipe FaceMesh not loaded');
      startFallbackDetection();
      return;
    }

    faceMesh = new FaceMesh({locateFile: (file) => {
      return `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`;
    }});

    faceMesh.setOptions({
      maxNumFaces:          1,
      refineLandmarks:      true,
      minDetectionConfidence: 0.5,
      minTrackingConfidence:  0.5,
    });

    faceMesh.onResults(onFaceResults);

    // Request webcam
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width:640, height:480, facingMode:'user' }
    });
    video.srcObject = stream;
    video.style.display = 'block';

    const placeholder = document.getElementById('feed-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    // Use MediaPipe Camera
    mpCamera = new Camera(video, {
      onFrame: async () => {
        await faceMesh.send({image: video});
      },
      width: 640,
      height: 480,
    });

    mpCamera.start();
    console.log('✅ MediaPipe FaceMesh running in browser!');

    // Start session timer
    if (typeof startSessionTimer === 'function') startSessionTimer();

    // Init focus chart
    initFocusChart();

    // Draw corner brackets
    drawCornerBrackets();

  } catch (err) {
    console.error('MediaPipe init error:', err);
    startFallbackDetection();
  }
}

// ── Focus Chart ───────────────────────────────────────────
function initFocusChart() {
  const ctx = document.getElementById('focus-chart');
  if (!ctx) return;
  const g = ctx.getContext('2d').createLinearGradient(0,0,0,200);
  g.addColorStop(0,'rgba(168,85,247,0.45)');
  g.addColorStop(1,'rgba(168,85,247,0)');
  window.focusChartObj = new Chart(ctx, {
    type:'line',
    data:{labels:focusLabels, datasets:[{
      label:'Focus', data:focusData,
      borderColor:'#a855f7', backgroundColor:g,
      borderWidth:2, pointRadius:0, tension:0.4, fill:true
    }]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},maxTicksLimit:6}},
        y:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},callback:v=>`${v}%`}}
      }
    }
  });
}

// ── Corner brackets overlay ───────────────────────────────
function drawCornerBrackets() {
  const canvas = document.getElementById('detection-canvas');
  const video  = document.getElementById('webcam-feed');
  if (!canvas || !video) return;
  const ctx = canvas.getContext('2d');

  function draw() {
    canvas.width  = video.offsetWidth  || 400;
    canvas.height = video.offsetHeight || 300;
    const cx=canvas.width/2, cy=canvas.height/2;
    const w=canvas.width*0.4, h=canvas.height*0.7;
    const bx=cx-w/2, by=cy-h/2, bl=24;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='rgba(168,85,247,0.7)';
    ctx.lineWidth=2; ctx.shadowBlur=10; ctx.shadowColor='#a855f7';
    [[bx,by,1,1],[bx+w,by,-1,1],[bx,by+h,1,-1],[bx+w,by+h,-1,-1]].forEach(([x,y,dx,dy])=>{
      ctx.beginPath(); ctx.moveTo(x+dx*bl,y); ctx.lineTo(x,y); ctx.lineTo(x,y+dy*bl); ctx.stroke();
    });
    // Scan line
    const scanY = by+(Date.now()%3000)/3000*h;
    const sg=ctx.createLinearGradient(bx,scanY,bx+w,scanY);
    sg.addColorStop(0,'transparent'); sg.addColorStop(0.5,'rgba(168,85,247,0.4)'); sg.addColorStop(1,'transparent');
    ctx.fillStyle=sg; ctx.shadowBlur=0;
    ctx.fillRect(bx,scanY-1,w,2);
    requestAnimationFrame(draw);
  }
  draw();
}

// ── Fallback if MediaPipe CDN fails ──────────────────────
function startFallbackDetection() {
  console.log('Using backend simulation mode');
  const obsLabel = document.getElementById('obs-timer-label');
  if (obsLabel) { obsLabel.textContent='Simulation mode (no CDN)'; obsLabel.style.color='#eab308'; }

  // Use existing app.js detection
  if (typeof initWebcam === 'function') initWebcam();
}

// ── Start on DOM ready ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Small delay to let MediaPipe scripts load
  setTimeout(initMediaPipe, 1000);
});
