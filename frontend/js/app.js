const API = 'http://localhost:5000/api';
let sessionStartTime  = null;
let sessionTimer      = null;
let detectionInterval = null;
let frameCapInterval  = null;
let focusChart = null, cognitiveChart = null, distributionChart = null, weeklyChart = null;
let isCameraOn   = false;
let videoStream  = null;
let captureCanvas = null;
let currentUser  = JSON.parse(localStorage.getItem('cognisense_user') || '{"username":"Shrushti","id":1}');

// Chart data buffers
let focusData   = Array.from({length:20}, ()=>0);
let focusLabels = Array.from({length:20}, (_,i)=>{
  const d=new Date(); d.setSeconds(d.getSeconds()-(19-i)*5);
  return `${d.getHours()}:${d.getMinutes().toString().padStart(2,'0')}`;
});

// ========================
// CLOCK
// ========================
function startClock() {
  const el = document.getElementById('live-clock');
  if (!el) return;
  const tick = ()=>{ el.textContent = new Date().toLocaleTimeString('en-US',{hour12:false}); };
  tick(); setInterval(tick, 1000);
}

// ========================
// USER
// ========================
function setUserDisplay() {
  const n=document.getElementById('user-name'), a=document.getElementById('user-avatar');
  if(n) n.textContent=currentUser.username;
  if(a) a.textContent=currentUser.username.charAt(0).toUpperCase();
}

// ========================
// NAV
// ========================
function setActiveNav() {
  const page = window.location.pathname.split('/').pop().replace('.html','');
  document.querySelectorAll('.nav-item').forEach(item=>{
    item.classList.toggle('active',
      item.dataset.page===page || (page===''&&item.dataset.page==='dashboard'));
  });
}

function logout() {
  stopDetection(); stopSessionTimer();
  localStorage.removeItem('cognisense_user');
  window.location.href='../index.html';
}

// ========================
// SESSION TIMER
// ========================
function startSessionTimer() {
  sessionStartTime = Date.now();
  const el=document.getElementById('session-time');
  const topEl=document.getElementById('topbar-session-time');
  clearInterval(sessionTimer);
  sessionTimer = setInterval(()=>{
    const e=Date.now()-sessionStartTime;
    const t=`${String(Math.floor(e/3600000)).padStart(2,'0')}:${String(Math.floor((e%3600000)/60000)).padStart(2,'0')}:${String(Math.floor((e%60000)/1000)).padStart(2,'0')}`;
    if(el) el.textContent=t;
    if(topEl) topEl.textContent=t;
  }, 1000);
}
function stopSessionTimer(){ clearInterval(sessionTimer); }

// ========================
// RING CHART
// ========================
function updateRing(percent, state) {
  const circle=document.getElementById('cognitive-ring');
  const pctEl=document.getElementById('ring-pct');
  const stateEl=document.getElementById('ring-state');
  const msgEl=document.getElementById('ring-msg');
  if(!circle) return;

  if(state==='Analyzing...'){
    circle.style.stroke='#475569';
    circle.style.strokeDashoffset=339.3;
    if(pctEl)   pctEl.textContent='...';
    if(stateEl) { stateEl.textContent='Observing'; stateEl.style.color='#475569'; }
    if(msgEl)   { msgEl.textContent='Collecting data...'; msgEl.style.color='#475569'; }
    return;
  }

  const circumference=339.3;
  circle.style.strokeDashoffset = circumference-(percent/100)*circumference;

  const colors={Focused:'#22c55e', Distracted:'#eab308', Stressed:'#ef4444'};
  const col=colors[state]||'#a855f7';
  circle.style.stroke=col;

  if(pctEl)   pctEl.textContent=`${percent}%`;
  if(stateEl) { stateEl.textContent=state; stateEl.style.color=col; }
  if(msgEl)   {
    const msgs={Focused:'You are doing great! 🎯',Distracted:'Try to refocus... 👀',Stressed:'Take a deep breath 🧘'};
    msgEl.textContent=msgs[state]||'';
    msgEl.style.color=col;
  }
}

// ========================
// OBSERVATION TIMER BAR
// ========================
function updateObservationTimer(progress, secsLeft, isObserving) {
  const bar   = document.getElementById('obs-progress-bar');
  const label = document.getElementById('obs-timer-label');
  const badge = document.getElementById('obs-status-badge');

  if(bar)   bar.style.width=`${progress}%`;
  if(label) {
    if(isObserving) {
      label.textContent=`Observing... ${secsLeft}s`;
      label.style.color='var(--cyan)';
    } else {
      label.textContent='Analysis complete ✓';
      label.style.color='var(--green)';
    }
  }
  if(badge) {
    badge.textContent = isObserving ? `⏱ ${secsLeft}s` : '✓ Done';
    badge.style.background = isObserving ? 'rgba(6,182,212,0.15)' : 'rgba(34,197,94,0.15)';
    badge.style.color = isObserving ? 'var(--cyan)' : 'var(--green)';
  }
}

// ========================
// EMOTION BADGE
// ========================
function updateEmotionBadge(emotion, confidence) {
  const el=document.getElementById('emotion-badge');
  if(!el) return;
  const icons={Happy:'😊',Sad:'😢',Angry:'😠',Neutral:'😐'};
  const colors={Happy:'rgba(34,197,94,0.15)',Sad:'rgba(14,165,233,0.15)',Angry:'rgba(239,68,68,0.15)',Neutral:'rgba(168,85,247,0.15)'};
  el.textContent=`${icons[emotion]||'🧠'} ${emotion}${confidence?' '+confidence+'%':''}`;
  el.style.background=colors[emotion]||'rgba(168,85,247,0.15)';
}

// ========================
// CAPTURE FRAME FROM VIDEO
// ========================
function captureFrame() {
  const video=document.getElementById('webcam-feed');
  if(!video||!video.videoWidth||video.paused) return null;
  if(!captureCanvas) {
    captureCanvas=document.createElement('canvas');
  }
  captureCanvas.width  = video.videoWidth;
  captureCanvas.height = video.videoHeight;
  captureCanvas.getContext('2d').drawImage(video,0,0);
  // Return compressed JPEG base64
  return captureCanvas.toDataURL('image/jpeg', 0.6);
}

// ========================
// DETECTION LOOP
// Every 500ms — captures frame, sends to backend
// ========================
function startDetection() {
  if(detectionInterval) return;

  detectionInterval = setInterval(async ()=>{
    const frameB64 = captureFrame();

    try {
      const res  = await fetch(`${API}/detect`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          user_id:  currentUser.id,
          frame:    frameB64 || null,
          emotion:  'Neutral',
        })
      });
      const json = await res.json();
      if(json.success) updateDashboardMetrics(json.data);
    } catch(e) {
      // Backend offline — show collecting state
      updateObservationTimer(0, 5, true);
    }
  }, 500);
}

function stopDetection() {
  clearInterval(detectionInterval);
  detectionInterval=null;
}

// ========================
// UPDATE ALL DASHBOARD METRICS
// ========================
function updateDashboardMetrics(data) {
  // Ring
  updateRing(data.focus_score||0, data.state||'Analyzing...');

  // Observation timer
  updateObservationTimer(
    data.window_progress||0,
    data.window_secs_left||5,
    data.is_observing!==false
  );

  // Metric cards
  setText('metric-focus',       data.state==='Analyzing...' ? '--' : `${data.focus_score||0}%`);
  setText('metric-distraction', data.state==='Analyzing...' ? '--' : `${data.distraction||0}%`);
  setText('metric-stress',      data.state==='Analyzing...' ? '--' : `${data.stress||0}%`);
  setText('metric-blink',       data.blink_rate>0 ? `${data.blink_rate}/min` : '--');

  // Quick stats
  setText('qs-focus', data.state==='Analyzing...' ? 'Wait...' : `${data.focus_score||0}%`);
  const qst=document.getElementById('qs-stress');
  if(qst){
    const level=data.stress>60?'High':data.stress>30?'Medium':'Low';
    qst.innerHTML=data.state==='Analyzing...'
      ?'<span style="color:var(--text-muted)">Wait...</span>'
      :`<span class="badge badge-${level==='High'?'stressed':level==='Medium'?'distracted':'focused'}">${level}</span>`;
  }

  // Biometric bars
  updateProgressBar('bar-attention',  data.attention||0,    '#a855f7,#6366f1');
  updateProgressBar('bar-eye',        data.eye_consistency||0, '#06b6d4,#0ea5e9');
  updateProgressBar('bar-head',       data.head_stability||0,  '#22c55e,#0ea5e9');
  updateProgressBar('bar-blink-vis',  Math.min(100,(data.blink_rate||0)/35*100), '#eab308,#f97316');

  // Labels
  setText('label-attention',  data.attention>0 ? `${Math.round(data.attention)}%` : '--');
  setText('label-eye',        data.eye_consistency>0 ? `${Math.round(data.eye_consistency)}%` : '--');
  setText('label-head',       data.head_movement||'--');
  setText('label-looking',    data.looking_forward!==undefined ? (data.looking_forward?'Forward ✓':'Away ✗') : '--');

  // Blink counter
  setText('live-blink-count',  data.blinks_this_window!==undefined ? data.blinks_this_window : '--');
  setText('total-blink-count', data.blink_total!==undefined ? data.blink_total : '--');

  // Emotion
  if(data.emotion) updateEmotionBadge(data.emotion, data.emotion_confidence||null);

  // Focus chart — only add real data points
  if(data.state && data.state!=='Analyzing...' && data.focus_score>0) {
    updateFocusChart(data.focus_score);
  }

  // Alerts
  addAlertIfNeeded(data);

  // Recommendations
  if(data.recommendations&&data.recommendations.length) updateRecommendations(data.recommendations);
}

function setText(id, val) {
  const el=document.getElementById(id); if(el) el.textContent=val;
}

function updateProgressBar(id, pct, gradient) {
  const el=document.getElementById(id);
  if(el){ el.style.width=`${Math.round(Math.max(0,Math.min(100,pct)))}%`; el.style.background=`linear-gradient(90deg,${gradient})`; }
}

// ========================
// ALERTS
// ========================
function addAlertIfNeeded(data) {
  const container=document.getElementById('live-alerts');
  if(!container) return;

  let msg=null, type='info', icon='💡';

  if(data.fake_detected)                          { msg='⚠️ Unnatural behavior detected';       type='warning'; icon='⚠️'; }
  else if(data.state==='Stressed')                { msg='😰 High stress detected';               type='danger';  icon='🚨'; }
  else if(data.state==='Distracted')              { msg='👀 Distraction detected — refocus!';    type='warning'; icon='⚠️'; }
  else if(!data.looking_forward&&data.face_ratio>50){ msg='👁️ Looking away from screen';          type='info';    icon='👁️'; }

  if(msg){
    const item=document.createElement('div');
    item.className=`alert-item ${type}`;
    item.innerHTML=`<div class="alert-icon">${icon}</div>
      <div class="alert-text"><p>${msg}</p><span>Just now</span></div>`;
    item.style.animation='fadeInUp 0.4s ease';
    container.prepend(item);
    if(container.children.length>5) container.lastElementChild.remove();
  }
}

// ========================
// RECOMMENDATIONS
// ========================
function updateRecommendations(recs) {
  const c=document.getElementById('rec-list');
  if(!c||!recs.length) return;
  c.innerHTML=recs.map(r=>`
    <div class="rec-item">
      <div class="rec-icon">${r.icon}</div>
      <div class="rec-text"><p>${r.text}</p><span>${r.reason}</span></div>
    </div>`).join('');
}

// ========================
// WEBCAM
// ========================
function initWebcam() {
  const video       = document.getElementById('webcam-feed');
  const placeholder = document.getElementById('feed-placeholder');
  if(!video) return;

  navigator.mediaDevices.getUserMedia({video:{width:640,height:480,facingMode:'user'}})
    .then(stream=>{
      videoStream = stream;
      video.srcObject = stream;
      video.style.display = 'block';
      if(placeholder) placeholder.style.display='none';
      isCameraOn = true;
      startDetection();
      startSessionTimer();
      drawFaceOverlay();
    })
    .catch(()=>{
      if(placeholder) placeholder.innerHTML=`
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="width:48px;height:48px;opacity:0.3"><path d="M15 10l4.55-2.55A1 1 0 0 1 21 8.4v7.2a1 1 0 0 1-1.45.9L15 14M3 8a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z"/></svg>
        <p style="font-size:13px;color:var(--text-muted)">Camera access denied<br><small>Running in simulation mode</small></p>`;
      // Still start detection — server will simulate
      startDetection();
      startSessionTimer();
    });
}

function toggleCamera() {
  const video=document.getElementById('webcam-feed');
  if(!video) return;
  video.paused ? video.play() : video.pause();
}

// ========================
// FACE OVERLAY (canvas)
// ========================
function drawFaceOverlay() {
  const canvas=document.getElementById('detection-canvas');
  const video=document.getElementById('webcam-feed');
  if(!canvas||!video) return;
  const ctx=canvas.getContext('2d');

  function draw() {
    canvas.width  = video.offsetWidth||400;
    canvas.height = video.offsetHeight||300;
    const cx=canvas.width/2, cy=canvas.height/2;
    const w=canvas.width*0.35, h=canvas.height*0.60;
    ctx.clearRect(0,0,canvas.width,canvas.height);

    // Corner brackets
    ctx.strokeStyle='rgba(168,85,247,0.9)';
    ctx.lineWidth=2;
    ctx.shadowBlur=12;
    ctx.shadowColor='#a855f7';
    const bx=cx-w/2, by=cy-h/2, bl=22;
    [[bx,by,1,1],[bx+w,by,-1,1],[bx,by+h,1,-1],[bx+w,by+h,-1,-1]].forEach(([x,y,dx,dy])=>{
      ctx.beginPath(); ctx.moveTo(x+dx*bl,y); ctx.lineTo(x,y); ctx.lineTo(x,y+dy*bl); ctx.stroke();
    });

    // Scan line
    const scanY=by+(Date.now()%3000)/3000*h;
    const sg=ctx.createLinearGradient(bx,scanY,bx+w,scanY);
    sg.addColorStop(0,'transparent'); sg.addColorStop(0.5,'rgba(168,85,247,0.5)'); sg.addColorStop(1,'transparent');
    ctx.fillStyle=sg; ctx.shadowBlur=0;
    ctx.fillRect(bx,scanY-1,w,2);

    // Corner dots
    [[bx,by],[bx+w,by],[bx,by+h],[bx+w,by+h]].forEach(([x,y])=>{
      ctx.beginPath(); ctx.arc(x,y,3,0,Math.PI*2);
      ctx.fillStyle='#a855f7'; ctx.shadowBlur=8; ctx.shadowColor='#a855f7'; ctx.fill();
    });
    ctx.shadowBlur=0;
    requestAnimationFrame(draw);
  }
  draw();
}

function endSession() {
  stopDetection(); stopSessionTimer();
  // Reset engine
  fetch(`${API}/session/reset`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:currentUser.id})}).catch(()=>{});
  saveSession();
  const btn=document.querySelector('.btn-end-session');
  if(btn){ btn.textContent='Session Saved ✓'; setTimeout(()=>{ btn.textContent='End Session'; },2500); }
}

async function saveSession() {
  const focusEl=document.getElementById('metric-focus');
  const focus=focusEl?parseInt(focusEl.textContent)||0:0;
  try {
    await fetch(`${API}/history`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user_id:currentUser.id, duration:sessionStartTime?Math.floor((Date.now()-sessionStartTime)/1000):0, focus_score:focus})
    });
    showToast('Session saved! 📊');
  } catch { showToast('Session saved locally.'); }
}

// ========================
// CHARTS
// ========================
function initFocusChart() {
  const ctx=document.getElementById('focus-chart');
  if(!ctx) return;
  const g=ctx.getContext('2d').createLinearGradient(0,0,0,200);
  g.addColorStop(0,'rgba(168,85,247,0.45)'); g.addColorStop(1,'rgba(168,85,247,0)');
  focusChart=new Chart(ctx,{
    type:'line',
    data:{labels:focusLabels,datasets:[{label:'Focus Score',data:focusData,borderColor:'#a855f7',backgroundColor:g,borderWidth:2,pointRadius:0,pointHoverRadius:5,pointHoverBackgroundColor:'#a855f7',tension:0.4,fill:true}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{backgroundColor:'rgba(10,10,26,0.9)',borderColor:'rgba(168,85,247,0.4)',borderWidth:1,titleColor:'#f1f5f9',bodyColor:'#94a3b8'}},
      scales:{
        x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},maxTicksLimit:6}},
        y:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},callback:v=>`${v}%`}}
      }
    }
  });
}

function updateFocusChart(val) {
  if(!focusChart) return;
  focusData.push(val); if(focusData.length>20) focusData.shift();
  const now=new Date();
  focusLabels.push(`${now.getHours()}:${now.getMinutes().toString().padStart(2,'0')}`);
  if(focusLabels.length>20) focusLabels.shift();
  focusChart.data.labels=focusLabels;
  focusChart.data.datasets[0].data=focusData;
  focusChart.update('none');
}

function initCognitiveChart() {
  const ctx=document.getElementById('cognitive-chart'); if(!ctx) return;
  const g=ctx.getContext('2d').createLinearGradient(0,0,0,200);
  g.addColorStop(0,'rgba(99,102,241,0.45)'); g.addColorStop(1,'rgba(99,102,241,0)');
  cognitiveChart=new Chart(ctx,{type:'line',data:{labels:focusLabels.slice(),datasets:[{label:'Cognitive Load',data:Array(20).fill(0),borderColor:'#6366f1',backgroundColor:g,borderWidth:2,pointRadius:0,tension:0.4,fill:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},maxTicksLimit:6}},y:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10}}}}}});
}

function initDistributionChart() {
  const ctx=document.getElementById('distribution-chart'); if(!ctx) return;
  distributionChart=new Chart(ctx,{type:'doughnut',data:{labels:['Focused','Distracted','Stressed'],datasets:[{data:[60,25,15],backgroundColor:['rgba(34,197,94,0.85)','rgba(234,179,8,0.85)','rgba(239,68,68,0.85)'],borderColor:['#22c55e','#eab308','#ef4444'],borderWidth:2,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'65%',plugins:{legend:{position:'right',labels:{color:'#94a3b8',padding:16,font:{size:12},usePointStyle:true}},tooltip:{backgroundColor:'rgba(10,10,26,0.9)'}}}});
}

function initWeeklyChart() {
  const ctx=document.getElementById('weekly-chart'); if(!ctx) return;
  weeklyChart=new Chart(ctx,{type:'bar',data:{labels:['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],datasets:[{label:'Focus',data:[72,78,65,82,74,60,70],backgroundColor:'rgba(168,85,247,0.7)',borderColor:'#a855f7',borderWidth:1,borderRadius:6},{label:'Stress',data:[20,15,30,12,22,35,18],backgroundColor:'rgba(239,68,68,0.5)',borderColor:'#ef4444',borderWidth:1,borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#94a3b8',font:{size:11},usePointStyle:true}},tooltip:{backgroundColor:'rgba(10,10,26,0.9)'}},scales:{x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569'}},y:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',callback:v=>`${v}%`}}}}});
}

function initEmotionChart() {
  const ctx=document.getElementById('emotion-chart'); if(!ctx) return;
  new Chart(ctx,{type:'doughnut',data:{labels:['Happy','Neutral','Sad','Angry'],datasets:[{data:[38,32,18,12],backgroundColor:['rgba(34,197,94,0.85)','rgba(168,85,247,0.85)','rgba(14,165,233,0.85)','rgba(239,68,68,0.85)'],borderColor:['#22c55e','#a855f7','#0ea5e9','#ef4444'],borderWidth:2,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'60%',plugins:{legend:{position:'right',labels:{color:'#94a3b8',padding:14,font:{size:12},usePointStyle:true}}}}});
}

// ========================
// SESSION HISTORY
// ========================
async function loadSessionHistory() {
  const tbody=document.getElementById('sessions-tbody'); if(!tbody) return;
  const mock=[
    {id:'S001',date:'23 May 2024',duration:'01:15:30',focus:85,status:'Focused',stress:'Low'},
    {id:'S002',date:'23 May 2024',duration:'00:45:20',focus:62,status:'Distracted',stress:'Medium'},
    {id:'S003',date:'22 May 2024',duration:'01:30:10',focus:75,status:'Focused',stress:'Low'},
    {id:'S004',date:'22 May 2024',duration:'00:30:45',focus:40,status:'Stressed',stress:'High'},
    {id:'S005',date:'21 May 2024',duration:'02:00:00',focus:91,status:'Focused',stress:'Low'},
  ];
  let sessions=mock;
  try {
    const res=await fetch(`${API}/history?user_id=${currentUser.id}`);
    const json=await res.json();
    if(json.sessions&&json.sessions.length) sessions=json.sessions;
  } catch{}
  tbody.innerHTML=sessions.map(s=>`<tr>
    <td><span style="color:var(--purple);font-weight:600;font-family:var(--font-display)">#${s.id}</span></td>
    <td>${s.date}</td>
    <td style="font-family:var(--font-display)">${s.duration}</td>
    <td style="font-family:var(--font-display);color:${s.focus>=70?'#22c55e':s.focus>=50?'#eab308':'#ef4444'}">${s.focus}%</td>
    <td><span class="badge badge-${s.status.toLowerCase()}">${s.status}</span></td>
    <td><span class="badge badge-${s.stress==='Low'?'focused':s.stress==='High'?'stressed':'distracted'}">${s.stress}</span></td>
    <td><button style="background:none;border:none;cursor:pointer;color:var(--blue)" onclick="showToast('Session #${s.id} details')">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
    </button></td></tr>`).join('');
}

// ========================
// PLANNER
// ========================
function toggleSession(el) {
  const check=el.querySelector('.session-check'), done=check.classList.contains('done');
  check.classList.toggle('done',!done); check.innerHTML=done?'':'✓'; el.classList.toggle('completed',!done);
  const all=document.querySelectorAll('.planner-session').length;
  const comp=document.querySelectorAll('.planner-session.completed').length;
  const pct=Math.round(comp/all*100);
  const bar=document.getElementById('progress-bar'), pctEl=document.getElementById('progress-pct');
  if(bar) bar.style.width=`${pct}%`; if(pctEl) pctEl.textContent=`${pct}%`;
}

// ========================
// SETTINGS
// ========================
function saveSettings() {
  const s={};
  document.querySelectorAll('.setting-toggle').forEach(t=>{ s[t.id]=t.checked; });
  localStorage.setItem('cognisense_settings',JSON.stringify(s));
  showToast('Settings saved! ✅');
}

function loadSettings() {
  const s=JSON.parse(localStorage.getItem('cognisense_settings')||'{}');
  Object.entries(s).forEach(([id,val])=>{ const el=document.getElementById(id); if(el) el.checked=val; });
}

// ========================
// TOAST
// ========================
function showToast(msg, type='success') {
  const t=document.createElement('div');
  t.style.cssText=`position:fixed;bottom:24px;right:24px;z-index:9999;background:rgba(10,10,26,0.95);border:1px solid ${type==='success'?'rgba(34,197,94,0.4)':'rgba(168,85,247,0.4)'};color:var(--text-primary);padding:14px 22px;border-radius:12px;font-size:14px;font-weight:500;box-shadow:0 8px 32px rgba(0,0,0,0.4);animation:fadeInUp 0.3s ease;backdrop-filter:blur(12px);`;
  t.textContent=msg;
  document.body.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='opacity 0.3s'; setTimeout(()=>t.remove(),300); },2500);
}

function updateNotifBadge(c){ const el=document.getElementById('notif-count'); if(el) el.textContent=c; }

// ========================
// INIT
// ========================
document.addEventListener('DOMContentLoaded', ()=>{
  startClock(); setUserDisplay(); setActiveNav(); loadSettings();
  const page=window.location.pathname.split('/').pop().replace('.html','');

  if(page==='dashboard'||page===''){
    initWebcam(); initFocusChart(); updateNotifBadge(3);
    updateRing(0,'Analyzing...');
  }
  if(page==='analytics'){
    initFocusChart(); initCognitiveChart(); initDistributionChart(); initWeeklyChart(); initEmotionChart();
    fetch(`${API}/analytics/summary?user_id=${currentUser.id}&period=today`).then(r=>r.json()).then(d=>{
      if(!d.success) return;
      const s=d.stats;
      setText('astat-avg-focus',`${s.avg_focus}%`); setText('astat-sessions',s.total_sessions);
      setText('astat-study-time',s.total_duration); setText('astat-distractions',s.total_distractions);
      setText('astat-focus-delta',`${s.focus_delta>=0?'↑':'↓'} ${Math.abs(s.focus_delta)}% from yesterday`);
    }).catch(()=>{});
  }
  if(page==='sessions') loadSessionHistory();
  if(page==='settings') loadSettings();

  // Entrance animations
  document.querySelectorAll('.glass-card,.stat-card,.metric-card,.astat-card,.feed-card,.settings-section').forEach((el,i)=>{
    el.style.opacity='0'; el.style.transform='translateY(18px)';
    setTimeout(()=>{ el.style.transition='opacity 0.5s ease,transform 0.5s ease'; el.style.opacity='1'; el.style.transform='translateY(0)'; },i*60+80);
  });
});
