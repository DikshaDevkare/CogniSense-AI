const API_URL = 'http://localhost:5000/api';
const MODEL_URL = '../models';

let isRunning = false, videoEl = null, overlayCanvas = null, overlayCtx = null;
let isBlinking = false, blinkStart = 0, blinksWindow = 0, totalBlinks = 0, blinkTimes = [];
let windowStart = Date.now(), windowFrames = 0, faceFrames = 0;
let earHistory = [], yawHistory = [], pitchHistory = [], attentionHist = [], expressionHist = {};
let windowNumber = 0, lastResult = null, sessionStart = Date.now();
let focusHistory = [], chartLabels = [], chartObj = null;
const WINDOW_MS = 5000, EAR_THRESH = 0.22;

function d(a,b){return Math.sqrt((a.x-b.x)**2+(a.y-b.y)**2);}

function getEAR(pts){
  const lA=d(pts[37],pts[41]),lB=d(pts[38],pts[40]),lC=d(pts[36],pts[39]);
  const rA=d(pts[43],pts[47]),rB=d(pts[44],pts[46]),rC=d(pts[42],pts[45]);
  return ((lA+lB)/(2*lC+1e-6)+(rA+rB)/(2*rC+1e-6))/2;
}

function getHeadAngles(pts){
  const yaw=(pts[30].x-(pts[36].x+pts[45].x)/2)/Math.abs(pts[45].x-pts[36].x+1e-6)*60;
  const pitch=((pts[30].y-pts[27].y)/Math.abs(pts[8].y-pts[27].y+1e-6)-0.5)*60;
  return{yaw:Math.round(yaw*10)/10,pitch:Math.round(pitch*10)/10};
}

function detectBlink(ear){
  const now=Date.now();
  if(ear<EAR_THRESH){if(!isBlinking){isBlinking=true;blinkStart=now;}}
  else{if(isBlinking){const dur=now-blinkStart;if(dur>=50&&dur<=400){blinksWindow++;totalBlinks++;blinkTimes.push(now);}isBlinking=false;}}
  blinkTimes=blinkTimes.filter(t=>t>now-60000);
}

function getBlinkRate(){
  const el=Math.min(60,(Date.now()-sessionStart)/1000);
  return el<3?0:Math.round(blinkTimes.length/el*60*10)/10;
}

function stdDev(a){
  if(a.length<2)return 0;
  const m=a.reduce((x,y)=>x+y,0)/a.length;
  return Math.sqrt(a.reduce((s,v)=>s+(v-m)**2,0)/a.length);
}

function computeWindow(){
  if(Date.now()-windowStart<WINDOW_MS)return null;
  const faceRatio=faceFrames/Math.max(windowFrames,1);
  const headStab=yawHistory.length>3?Math.max(0,Math.min(100,100-(stdDev(yawHistory)+stdDev(pitchHistory))*2.5)):50;
  const avgAttn=attentionHist.length?attentionHist.reduce((a,b)=>a+b,0)/attentionHist.length:0;
  const earStd=stdDev(earHistory);
  const eyeConsist=earStd>=0.006&&earStd<=0.09?Math.min(100,50+earStd*500):earStd<0.006?20:Math.max(10,80-earStd*250);
  let domEmo='neutral',maxC=0;
  Object.entries(expressionHist).forEach(([k,v])=>{if(v>maxC){maxC=v;domEmo=k;}});
  const emoMods={happy:{f:15,s:-5},neutral:{f:5,s:0},sad:{f:-10,s:15},angry:{f:-15,s:20},fearful:{f:-10,s:15},disgusted:{f:-10,s:10},surprised:{f:-5,s:5}};
  const emo=emoMods[domEmo]||emoMods.neutral;
  const br=getBlinkRate();
  let focus=0,stress=0,distract=0;
  if(avgAttn>=80)focus+=30;else if(avgAttn>=60){focus+=20;distract+=5;}else if(avgAttn>=40){focus+=10;distract+=15;}else distract+=25;
  if(headStab>=80)focus+=20;else if(headStab>=55){focus+=12;distract+=5;}else{distract+=15;stress+=5;}
  if(br===0)distract+=10;else if(br>=10&&br<=20)focus+=20;else if(br>28){stress+=22;distract+=5;}else if(br>22){stress+=12;focus+=5;}else if(br<6){focus+=15;stress+=5;}else focus+=10;
  if(eyeConsist>=75)focus+=15;else if(eyeConsist>=50){focus+=8;distract+=5;}else distract+=10;
  if(faceRatio>=0.85)focus+=10;else if(faceRatio>=0.5){focus+=5;distract+=5;}else distract+=10;
  focus=Math.max(0,focus+emo.f);stress=Math.max(0,stress-emo.s);
  const mins=(Date.now()-sessionStart)/60000;
  if(mins>90){stress+=8;focus=Math.max(0,focus-5);}else if(mins>60)stress+=4;
  const total=Math.max(focus+stress+distract,1);
  const focusPct=Math.min(100,Math.round(focus/total*100));
  const stressPct=Math.min(100,Math.round(stress/total*100));
  const distrPct=Math.min(100,Math.round(distract/total*100));
  let state='Focused';
  if(focusPct<55&&stressPct>=38)state='Stressed';
  else if(focusPct<55)state='Distracted';
  const emoLabels={happy:'Happy',neutral:'Neutral',sad:'Sad',angry:'Angry',fearful:'Fear',disgusted:'Disgust',surprised:'Surprise'};
  const emoIcons={happy:'😊',neutral:'😐',sad:'😢',angry:'😠',fearful:'😨',disgusted:'😤',surprised:'😮'};
  const result={state,focusPct,stressPct,distrPct,blinkRate:br,headStab:Math.round(headStab),eyeConsist:Math.round(eyeConsist),avgAttn:Math.round(avgAttn),faceRatio:Math.round(faceRatio*100),emotion:emoLabels[domEmo]||'Neutral',emotionIcon:emoIcons[domEmo]||'😐',windowNumber:windowNumber++,sessMins:Math.round((Date.now()-sessionStart)/60000*10)/10};
  windowStart=Date.now();windowFrames=0;faceFrames=0;blinksWindow=0;earHistory=[];yawHistory=[];pitchHistory=[];attentionHist=[];expressionHist={};
  return result;
}

function setText(id,val){const el=document.getElementById(id);if(el)el.textContent=val;}
function setBar(id,pct,g){const el=document.getElementById(id);if(el){el.style.width=`${Math.max(0,Math.min(100,Math.round(pct||0)))}%`;el.style.background=`linear-gradient(90deg,${g})`;}}

function updateUI(result,live){
  if(!result)return;lastResult=result;
  const{state,focusPct,stressPct,distrPct,blinkRate,headStab,eyeConsist,avgAttn,emotion,emotionIcon}=result;
  const colors={Focused:'#22c55e',Distracted:'#eab308',Stressed:'#ef4444'};
  const col=colors[state]||'#a855f7';
  const ring=document.getElementById('cognitive-ring');
  if(ring){ring.style.strokeDashoffset=339.3-(focusPct/100)*339.3;ring.style.stroke=col;}
  setText('ring-pct',`${focusPct}%`);
  const stEl=document.getElementById('ring-state');if(stEl){stEl.textContent=state;stEl.style.color=col;}
  const msgEl=document.getElementById('ring-msg');
  if(msgEl){const msgs={Focused:'Great focus! 🎯',Distracted:'Try to refocus 👀',Stressed:'Deep breath 🧘'};msgEl.textContent=msgs[state]||'';msgEl.style.color=col;}
  setText('metric-focus',`${focusPct}%`);setText('metric-distraction',`${distrPct}%`);setText('metric-stress',`${stressPct}%`);
  setText('metric-blink',blinkRate>0?`${blinkRate}/min`:'--');setText('qs-focus',`${focusPct}%`);
  setText('live-blink-count',blinksWindow);setText('total-blink-count',totalBlinks);
  const qst=document.getElementById('qs-stress');
  if(qst){const lvl=stressPct>60?'High':stressPct>30?'Medium':'Low';const cls=lvl==='High'?'stressed':lvl==='Medium'?'distracted':'focused';qst.innerHTML=`<span class="badge badge-${cls}">${lvl}</span>`;}
  setBar('bar-attention',avgAttn,'#a855f7,#6366f1');setBar('bar-head',headStab,'#22c55e,#0ea5e9');setBar('bar-eye',eyeConsist,'#06b6d4,#0ea5e9');setBar('bar-gaze',live&&live.lookingFwd?85:15,'#eab308,#f97316');
  setText('label-attention',`${avgAttn}%`);setText('label-head',headStab>=70?'Stable':'Moving');setText('label-eye',`${eyeConsist}%`);setText('label-looking',live&&live.lookingFwd?'Forward ✓':'Away ✗');
  const emoBadge=document.getElementById('emotion-badge');
  if(emoBadge){emoBadge.textContent=`${emotionIcon} ${emotion}`;const ec={Happy:'rgba(34,197,94,0.15)',Neutral:'rgba(168,85,247,0.15)',Sad:'rgba(14,165,233,0.15)',Angry:'rgba(239,68,68,0.15)'};emoBadge.style.background=ec[emotion]||'rgba(168,85,247,0.15)';}
  if(focusHistory.length>=20){focusHistory.shift();chartLabels.shift();}
  focusHistory.push(focusPct);const now=new Date();chartLabels.push(`${now.getHours()}:${now.getMinutes().toString().padStart(2,'0')}`);
  if(chartObj){chartObj.data.labels=chartLabels;chartObj.data.datasets[0].data=focusHistory;chartObj.update('none');}
  const container=document.getElementById('live-alerts');
  if(container){let msg=null,type='info',icon='💡';
    if(state==='Stressed'){msg='😰 High stress detected!';type='danger';icon='🚨';}
    else if(state==='Distracted'){msg='👀 Distraction — refocus!';type='warning';icon='⚠️';}
    else if(state==='Focused'){msg='✅ Good focus maintained';type='success';icon='🎯';}
    if(msg){const item=document.createElement('div');item.className=`alert-item ${type}`;item.innerHTML=`<div class="alert-icon">${icon}</div><div class="alert-text"><p>${msg}</p><span>Just now</span></div>`;item.style.animation='fadeInUp 0.4s ease';container.prepend(item);while(container.children.length>5)container.lastElementChild.remove();}}
  const rc=document.getElementById('rec-list');
  if(rc){const recs=[];const m=result.sessMins||0,br2=result.blinkRate||0;
    if(m>45)recs.push({icon:'☕',text:'Take a 5-min break',reason:`${Math.round(m)} min of study`});
    if(br2<8&&br2>0)recs.push({icon:'👁️',text:'Blink more frequently',reason:'Eye strain risk'});
    if(br2>25)recs.push({icon:'🧘',text:'Deep breathing',reason:'High stress signals'});
    if(state==='Distracted')recs.push({icon:'🎯',text:'Try Pomodoro technique',reason:'Focus inconsistent'});
    if(recs.length===0)recs.push({icon:'🏆',text:'Keep it up!',reason:'Excellent performance'});
    rc.innerHTML=recs.slice(0,4).map(r=>`<div class="rec-item"><div class="rec-icon">${r.icon}</div><div class="rec-text"><p>${r.text}</p><span>${r.reason}</span></div></div>`).join('');}
  try{fetch(API_URL+'/detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:(window.currentUser||{id:1}).id,no_frame:true,state:result.state,focus:result.focusPct,stress:result.stressPct,blink_rate:result.blinkRate,attention:result.avgAttn})});}catch{}
}

function drawOverlay(det){
  if(!overlayCtx||!videoEl)return;
  const w=overlayCanvas.width=videoEl.offsetWidth||640,h=overlayCanvas.height=videoEl.offsetHeight||480;
  overlayCtx.clearRect(0,0,w,h);
  const col=lastResult?({Focused:'#22c55e',Distracted:'#eab308',Stressed:'#ef4444'})[lastResult.state]||'#a855f7':'#a855f7';
  if(det&&det.landmarks){
    const pts=det.landmarks.positions,sx=w/(videoEl.videoWidth||640),sy=h/(videoEl.videoHeight||480);
    overlayCtx.fillStyle='rgba(168,85,247,0.9)';
    [36,37,38,39,40,41,42,43,44,45,46,47].forEach(i=>{overlayCtx.beginPath();overlayCtx.arc(pts[i].x*sx,pts[i].y*sy,2.5,0,Math.PI*2);overlayCtx.fill();});
    overlayCtx.fillStyle='rgba(6,182,212,1)';overlayCtx.beginPath();overlayCtx.arc(pts[30].x*sx,pts[30].y*sy,3.5,0,Math.PI*2);overlayCtx.fill();
    if(det.detection){const bx=det.detection.box,x=bx.x*sx,y=bx.y*sy,bw=bx.width*sx,bh=bx.height*sy,bl=22;
      overlayCtx.strokeStyle=col;overlayCtx.lineWidth=2;overlayCtx.shadowBlur=12;overlayCtx.shadowColor=col;
      [[x,y,1,1],[x+bw,y,-1,1],[x,y+bh,1,-1],[x+bw,y+bh,-1,-1]].forEach(([cx,cy,dx,dy])=>{overlayCtx.beginPath();overlayCtx.moveTo(cx+dx*bl,cy);overlayCtx.lineTo(cx,cy);overlayCtx.lineTo(cx,cy+dy*bl);overlayCtx.stroke();});
      overlayCtx.shadowBlur=0;}}
  const scanY=h*0.1+(Date.now()%3000)/3000*(h*0.8);
  const sg=overlayCtx.createLinearGradient(0,scanY,w,scanY);sg.addColorStop(0,'transparent');sg.addColorStop(0.5,`${col}55`);sg.addColorStop(1,'transparent');
  overlayCtx.fillStyle=sg;overlayCtx.fillRect(0,scanY-1,w,2);
}

function initChart(){
  const ctx=document.getElementById('focus-chart');if(!ctx)return;
  const g=ctx.getContext('2d').createLinearGradient(0,0,0,200);g.addColorStop(0,'rgba(168,85,247,0.45)');g.addColorStop(1,'rgba(168,85,247,0)');
  chartObj=new Chart(ctx,{type:'line',data:{labels:chartLabels,datasets:[{label:'Focus',data:focusHistory,borderColor:'#a855f7',backgroundColor:g,borderWidth:2,pointRadius:0,tension:0.4,fill:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},maxTicksLimit:6}},y:{min:0,max:100,grid:{color:'rgba(255,255,255,0.04)'},ticks:{color:'#475569',font:{size:10},callback:v=>`${v}%`}}}}});
}

async function detectionLoop(){
  if(!isRunning||!videoEl)return;
  const faceBadge=document.getElementById('face-status-badge');
  const obsBar=document.getElementById('obs-progress-bar');
  const obsLabel=document.getElementById('obs-timer-label');
  const obsBadge=document.getElementById('obs-status-badge');
  try{
    const det=await faceapi.detectSingleFace(videoEl,new faceapi.SsdMobilenetv1Options({minConfidence:0.25})).withFaceLandmarks().withFaceExpressions();
    windowFrames++;
    const elapsed=Date.now()-windowStart,prog=Math.min(100,Math.round(elapsed/WINDOW_MS*100));
    if(obsBar)obsBar.style.width=`${prog}%`;
    if(obsBadge)obsBadge.textContent=prog<100?`⏱ ${Math.max(0,((WINDOW_MS-elapsed)/1000).toFixed(1))}s`:'✓';
    if(!det){
      if(faceBadge){faceBadge.textContent='No Face ✗';faceBadge.style.background='rgba(239,68,68,0.2)';faceBadge.style.color='#ef4444';}
      if(obsLabel){obsLabel.textContent='No face — look at camera!';obsLabel.style.color='#ef4444';}
      drawOverlay(null);setText('live-blink-count',blinksWindow);setText('total-blink-count',totalBlinks);
      const win=computeWindow();if(win)updateUI(win,{lookingFwd:false});
    }else{
      faceFrames++;
      if(faceBadge){faceBadge.textContent='Face ✓';faceBadge.style.background='rgba(34,197,94,0.2)';faceBadge.style.color='#22c55e';}
      if(obsLabel){obsLabel.textContent=`Observing... ${Math.max(0,((WINDOW_MS-elapsed)/1000).toFixed(1))}s`;obsLabel.style.color='var(--cyan)';}
      const pts=det.landmarks.positions;
      const ear=getEAR(pts);earHistory.push(ear);detectBlink(ear);
      setText('live-blink-count',blinksWindow);setText('total-blink-count',totalBlinks);
      const{yaw,pitch}=getHeadAngles(pts);yawHistory.push(yaw);pitchHistory.push(pitch);
      const lookingFwd=Math.abs(yaw)<22&&Math.abs(pitch)<18;
      let attn=0;if(lookingFwd)attn+=40;if(Math.abs(yaw)<15)attn+=25;if(Math.abs(pitch)<12)attn+=20;if(ear>EAR_THRESH)attn+=15;attentionHist.push(attn);
      Object.entries(det.expressions).forEach(([k,v])=>{expressionHist[k]=(expressionHist[k]||0)+v;});
      drawOverlay(det);
      const win=computeWindow();
      if(win){if(obsLabel){obsLabel.textContent='Analysis complete ✓';obsLabel.style.color='var(--green)';}updateUI(win,{lookingFwd});}
    }
  }catch(err){console.error('Detection:',err.message);}
  setTimeout(detectionLoop,100);
}

async function initFaceAPI(){
  videoEl=document.getElementById('webcam-feed');
  overlayCanvas=document.getElementById('detection-canvas');
  if(!overlayCanvas)return;
  overlayCtx=overlayCanvas.getContext('2d');
  const obsLabel=document.getElementById('obs-timer-label');
  const faceBadge=document.getElementById('face-status-badge');
  try{
    if(typeof faceapi==='undefined'){if(obsLabel){obsLabel.textContent='Loading face-api.js...';obsLabel.style.color='#eab308';}console.error('faceapi not loaded');return;}
    if(obsLabel){obsLabel.textContent='Loading AI models...';obsLabel.style.color='var(--cyan)';}
    await Promise.all([faceapi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL),faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URL)]);
    console.log('✅ All models loaded!');
    if(obsLabel)obsLabel.textContent='Models loaded — starting camera...';
    const stream=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480,facingMode:'user'}});
    videoEl.srcObject=stream;videoEl.style.display='block';
    const ph=document.getElementById('feed-placeholder');if(ph)ph.style.display='none';
    await new Promise(res=>{videoEl.onloadedmetadata=res;});await videoEl.play();
    if(obsLabel){obsLabel.textContent='Camera ready — face dekho!';obsLabel.style.color='var(--green)';}
    isRunning=true;windowStart=Date.now();sessionStart=Date.now();
    setTimeout(detectionLoop,500);
    if(typeof startSessionTimer==='function')startSessionTimer();
    initChart();
    console.log('✅ CogniSense detection running!');
  }catch(err){
    console.error('Init error:',err);
    if(obsLabel){obsLabel.textContent='Error: '+err.message;obsLabel.style.color='#ef4444';}
    if(faceBadge){faceBadge.textContent='Error';faceBadge.style.color='#ef4444';}
  }
}

document.addEventListener('DOMContentLoaded',()=>{setTimeout(initFaceAPI,1200);});
