"""
SENTINEL AI - Real-Time Object Tracking
Using Google Gemini API (Fast & Reliable)
"""

from google import genai
from google.genai import types
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
import uvicorn
import os
import time
import json
import threading
import cv2
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

# Direct API Key
API_KEY = "AIzaSyAfdEnzBk0Aqh8O4oE989Vpj3JPRTjF-Kk"
client = genai.Client(api_key=API_KEY)
MODEL = "gemini-2.5-flash"

CAMERA_SOURCE = 0
Path("alerts").mkdir(exist_ok=True)

monitoring_active = False
monitoring_thread = None
alerts_history = []
last_analysis = None
detected_objects = []
stats = {"scans": 0, "alerts": 0, "humans": 0}
current_task = "Track all people and alert when person detected"

latest_frame = None
frame_lock = threading.Lock()


class CameraManager:
    def __init__(self):
        self.cap = None
        self.running = False
        self.thread = None
        
    def start(self):
        if not self.running:
            self.cap = cv2.VideoCapture(CAMERA_SOURCE)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            
    def _capture_loop(self):
        global latest_frame
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with frame_lock:
                        latest_frame = frame.copy()
            time.sleep(0.016)
            
    def get_frame(self):
        with frame_lock:
            return latest_frame.copy() if latest_frame is not None else None
            
    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()


camera_mgr = CameraManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    camera_mgr.start()
    yield
    camera_mgr.stop()


app = FastAPI(lifespan=lifespan)


def capture_frame():
    frame = camera_mgr.get_frame()
    if frame is not None:
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buffer.tobytes()
    return None


def generate_frames():
    while True:
        frame = camera_mgr.get_frame()
        if frame is not None:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.033)


def analyze_frame(image_data, task):
    prompt = f"""Analyze this frame. Task: "{task}"

Generate alert=true when you detect what user asked for.
Output ONLY valid JSON:
{{"alert":true,"alert_type":"info","alert_message":"Person detected","scene":"brief description","people_count":1,"tracked_objects":[{{"id":"person_1","label":"Person","conf":0.95,"x":30,"y":20,"w":25,"h":45,"color":"#00ff00"}}],"all_objects":["person"]}}

x,y,w,h are percentages. Colors: person=#00ff00, face=#00ffff, phone=#ffff00"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[types.Part.from_bytes(data=image_data, mime_type="image/jpeg"), prompt]
        )
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"alert": False, "scene": str(e), "people_count": 0, "tracked_objects": [], "all_objects": []}


def monitoring_loop():
    global monitoring_active, last_analysis, stats, alerts_history, detected_objects
    while monitoring_active:
        try:
            frame = capture_frame()
            if frame:
                stats["scans"] += 1
                result = analyze_frame(frame, current_task)
                result["time"] = datetime.now().strftime('%H:%M:%S')
                result["timestamp"] = time.time()
                last_analysis = result
                stats["humans"] = result.get("people_count", 0)
                detected_objects = result.get("tracked_objects", [])
                
                if result.get("alert", False):
                    stats["alerts"] += 1
                    alert = {
                        "id": stats["alerts"],
                        "time": result["time"],
                        "type": result.get("alert_type", "info"),
                        "message": result.get("alert_message", "Detection alert"),
                        "objects": len(detected_objects)
                    }
                    alerts_history.insert(0, alert)
                    with open(f"alerts/alert_{stats['alerts']}.jpg", 'wb') as f:
                        f.write(frame)
                    print(f"ALERT: {alert['message']}")
                    
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(0.5)


DASHBOARD = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>SENTINEL AI - Real-Time Tracking</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0a0f;color:#fff;overflow:hidden;height:100vh;width:100vw}
.app{display:grid;grid-template-columns:1fr 380px;height:100vh;width:100vw}

.video-area{position:relative;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden}
.video-container{position:relative;width:100%;height:100%}
#videoFeed{width:100%;height:100%;object-fit:cover}
#trackingCanvas{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none}

.hud-top{position:absolute;top:0;left:0;right:0;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;background:linear-gradient(180deg,rgba(0,0,0,0.9) 0%,transparent 100%)}
.hud-bottom{position:absolute;bottom:0;left:0;right:0;padding:20px 24px;background:linear-gradient(0deg,rgba(0,0,0,0.9) 0%,transparent 100%)}
.hud-item{font-family:'JetBrains Mono',monospace;font-size:13px;display:flex;align-items:center;gap:10px;font-weight:500}
.hud-item.live{color:#00ff00}
.hud-item.live::before{content:'';width:10px;height:10px;background:#ff0000;border-radius:50%;animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.4;transform:scale(0.8)}}
.hud-stats{display:flex;gap:24px}
.hud-stat{color:#00ff00;font-weight:500}
.hud-stat span{color:#fff}

.alert-banner{position:absolute;top:80px;left:50%;transform:translateX(-50%);background:#ff4444;color:#fff;padding:14px 28px;border-radius:10px;font-weight:600;font-size:14px;display:none;z-index:100;box-shadow:0 8px 32px rgba(255,68,68,0.5)}
.alert-banner.show{display:block;animation:alertPop 0.3s ease}
@keyframes alertPop{from{transform:translateX(-50%) scale(0.8);opacity:0}to{transform:translateX(-50%) scale(1);opacity:1}}

.left-alerts{position:absolute;top:80px;left:20px;width:280px;max-height:calc(100% - 160px);overflow-y:auto;z-index:50}
.left-alert{background:rgba(0,0,0,0.85);border:1px solid #00ff00;border-radius:10px;padding:12px 16px;margin-bottom:10px;display:flex;gap:12px;animation:slideIn 0.3s ease;backdrop-filter:blur(10px)}
@keyframes slideIn{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:translateX(0)}}
.left-alert-icon{width:32px;height:32px;background:rgba(0,255,0,0.2);border-radius:8px;display:flex;align-items:center;justify-content:center;color:#00ff00;font-size:14px;flex-shrink:0}
.left-alert-content{flex:1;min-width:0}
.left-alert-msg{font-size:12px;color:#fff;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.left-alert-time{font-size:10px;color:#888;margin-top:2px}

.panel{background:#0d0d14;border-left:1px solid #1a1a2e;display:flex;flex-direction:column;width:380px;height:100vh;overflow:hidden}
.panel-header{padding:20px;border-bottom:1px solid #1a1a2e;display:flex;align-items:center;gap:14px;flex-shrink:0}
.logo{width:44px;height:44px;background:#00ff00;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;color:#000;font-size:16px;font-family:'JetBrains Mono',monospace}
.title{font-size:18px;font-weight:700}
.subtitle{font-size:10px;color:#666;letter-spacing:2px;margin-top:2px}

.command-box{padding:16px 20px;border-bottom:1px solid #1a1a2e;flex-shrink:0}
.cmd-label{font-size:10px;color:#888;text-transform:uppercase;margin-bottom:8px;font-weight:600;letter-spacing:1px}
.cmd-input{width:100%;padding:12px 14px;background:#111118;border:1px solid #2a2a3e;border-radius:8px;color:#fff;font-size:13px}
.cmd-input:focus{outline:none;border-color:#00ff00}
.quick-cmds{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.qcmd{padding:6px 12px;background:#16161f;border:1px solid #2a2a3e;border-radius:6px;font-size:11px;color:#888;cursor:pointer;transition:all 0.15s}
.qcmd:hover{border-color:#00ff00;color:#00ff00}

.controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:16px 20px;border-bottom:1px solid #1a1a2e;flex-shrink:0}
.btn{padding:14px;border:none;border-radius:8px;font-weight:600;font-size:13px;cursor:pointer;transition:all 0.15s}
.btn-start{background:#00ff00;color:#000}
.btn-start:hover{background:#00dd00}
.btn-start:disabled{background:#2a2a3e;color:#555}
.btn-stop{background:#16161f;border:2px solid #ff4444;color:#ff4444}
.btn-stop:hover{background:#ff4444;color:#fff}
.btn-stop:disabled{border-color:#2a2a3e;color:#444}
.btn-scan{grid-column:span 2;background:#16161f;color:#fff;border:1px solid #2a2a3e}
.btn-scan:hover{border-color:#00ff00}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:16px 20px;border-bottom:1px solid #1a1a2e;flex-shrink:0}
.stat{background:#111118;border-radius:10px;padding:14px 8px;text-align:center;border:1px solid #1a1a2e}
.stat-val{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;color:#00ff00}
.stat-lbl{font-size:9px;color:#666;text-transform:uppercase;margin-top:4px;font-weight:500}

.analysis{flex:1;overflow-y:auto;padding:16px 20px;min-height:0}
.section-title{font-size:10px;color:#888;text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px;font-weight:600;letter-spacing:1px}
.section-title::before{content:'';width:6px;height:6px;background:#00ff00;border-radius:50%}
.analysis-text{font-size:13px;line-height:1.6;color:#999;margin-bottom:16px}
.objects-grid{display:flex;flex-wrap:wrap;gap:6px}
.obj-pill{padding:6px 12px;border-radius:6px;font-size:11px;font-weight:500}
.obj-pill.tracked{background:rgba(0,255,0,0.12);color:#00ff00;border:1px solid rgba(0,255,0,0.3)}
.obj-pill.other{background:#16161f;color:#666;border:1px solid #2a2a3e}

.alerts-section{border-top:1px solid #1a1a2e;flex-shrink:0;max-height:180px;overflow-y:auto}
.alerts-title{padding:12px 20px;font-size:10px;color:#888;text-transform:uppercase;background:#0d0d14;position:sticky;top:0;font-weight:600;letter-spacing:1px}
.alert-item{padding:12px 20px;border-bottom:1px solid #1a1a2e;display:flex;gap:12px}
.alert-icon{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0}
.alert-icon.info{background:rgba(0,255,0,0.15);color:#00ff00}
.alert-content{flex:1}
.alert-msg{font-size:12px;color:#fff;font-weight:500}
.alert-time{font-size:10px;color:#666;margin-top:2px}
.no-alerts{padding:30px;text-align:center;color:#444;font-size:12px}
</style>
</head>
<body>
<div class="app">
<div class="video-area">
<div class="video-container">
<img id="videoFeed" src="/video_feed">
<canvas id="trackingCanvas"></canvas>
</div>
<div class="hud-top">
<div class="hud-item live"><span id="statusText">LIVE</span></div>
<div class="hud-item" id="timeDisplay">00:00:00</div>
</div>
<div class="hud-bottom">
<div class="hud-stats">
<div class="hud-stat">TRACKING: <span id="hudTrack">0</span></div>
<div class="hud-stat">PEOPLE: <span id="hudPeople">0</span></div>
<div class="hud-stat">SCANS: <span id="hudScans">0</span></div>
<div class="hud-stat">ALERTS: <span id="hudAlerts">0</span></div>
</div>
</div>
<div class="alert-banner" id="alertBanner">Person Detected</div>
<div class="left-alerts" id="leftAlerts"></div>
</div>

<div class="panel">
<div class="panel-header">
<div class="logo">S</div>
<div><div class="title">SENTINEL AI</div><div class="subtitle">GEMINI VISION</div></div>
</div>

<div class="command-box">
<div class="cmd-label">Tracking Command</div>
<input type="text" class="cmd-input" id="cmdInput" value="Track all people and alert when detected">
<div class="quick-cmds">
<span class="qcmd" onclick="setCmd('Track all people')">People</span>
<span class="qcmd" onclick="setCmd('Track my face')">Face</span>
<span class="qcmd" onclick="setCmd('Track person with phone')">+Phone</span>
<span class="qcmd" onclick="setCmd('Track everything')">All</span>
</div>
</div>

<div class="controls">
<button class="btn btn-start" id="startBtn" onclick="startTracking()">START</button>
<button class="btn btn-stop" id="stopBtn" onclick="stopTracking()" disabled>STOP</button>
<button class="btn btn-scan" onclick="scanNow()">SCAN NOW</button>
</div>

<div class="stats">
<div class="stat"><div class="stat-val" id="statScans">0</div><div class="stat-lbl">Scans</div></div>
<div class="stat"><div class="stat-val" id="statTrack">0</div><div class="stat-lbl">Tracked</div></div>
<div class="stat"><div class="stat-val" id="statPeople">0</div><div class="stat-lbl">People</div></div>
<div class="stat"><div class="stat-val" id="statAlerts">0</div><div class="stat-lbl">Alerts</div></div>
</div>

<div class="analysis">
<div class="section-title">AI Analysis</div>
<div class="analysis-text" id="analysisText">Click START to begin tracking.</div>
<div class="section-title" style="margin-top:14px">Detected Objects</div>
<div class="objects-grid" id="objectsGrid"><span class="obj-pill other">Waiting...</span></div>
</div>

<div class="alerts-section">
<div class="alerts-title">Alert History</div>
<div id="alertsList"><div class="no-alerts">No alerts yet</div></div>
</div>
</div>
</div>

<script>
const canvas = document.getElementById('trackingCanvas');
const ctx = canvas.getContext('2d');
const video = document.getElementById('videoFeed');

let tracking = false;
let animatedObjects = [];
let refreshInterval;
let alertCount = 0;

function resizeCanvas() {
    canvas.width = video.offsetWidth;
    canvas.height = video.offsetHeight;
}
window.addEventListener('resize', resizeCanvas);
video.onload = resizeCanvas;
setTimeout(resizeCanvas, 300);

function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    animatedObjects.forEach(obj => {
        obj.cx += (obj.tx - obj.cx) * 0.15;
        obj.cy += (obj.ty - obj.cy) * 0.15;
        obj.cw += (obj.tw - obj.cw) * 0.15;
        obj.ch += (obj.th - obj.ch) * 0.15;
        
        const x = obj.cx * canvas.width / 100;
        const y = obj.cy * canvas.height / 100;
        const w = obj.cw * canvas.width / 100;
        const h = obj.ch * canvas.height / 100;
        const color = obj.color || '#00ff00';
        
        ctx.shadowColor = color;
        ctx.shadowBlur = 12;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        
        const cornerLen = Math.min(20, w/4, h/4);
        ctx.lineWidth = 3;
        
        ctx.beginPath();
        ctx.moveTo(x, y + cornerLen); ctx.lineTo(x, y); ctx.lineTo(x + cornerLen, y);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x + w - cornerLen, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + cornerLen);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x, y + h - cornerLen); ctx.lineTo(x, y + h); ctx.lineTo(x + cornerLen, y + h);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x + w - cornerLen, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - cornerLen);
        ctx.stroke();
        
        ctx.shadowBlur = 0;
        
        const label = obj.label + (obj.conf ? ' ' + Math.round(obj.conf * 100) + '%' : '');
        ctx.font = 'bold 12px JetBrains Mono, monospace';
        const textWidth = ctx.measureText(label).width;
        ctx.fillStyle = color;
        ctx.fillRect(x, y - 22, textWidth + 12, 20);
        ctx.fillStyle = '#000';
        ctx.fillText(label, x + 6, y - 7);
    });
    
    requestAnimationFrame(animate);
}

function updateTracking(objects) {
    if (!objects || objects.length === 0) {
        animatedObjects = [];
        return;
    }
    
    objects.forEach(newObj => {
        let existing = animatedObjects.find(o => o.id === newObj.id);
        if (existing) {
            existing.tx = newObj.x;
            existing.ty = newObj.y;
            existing.tw = newObj.w || 25;
            existing.th = newObj.h || 40;
            existing.conf = newObj.conf;
            existing.label = newObj.label || existing.label;
            existing.color = newObj.color || existing.color;
        } else {
            animatedObjects.push({
                id: newObj.id || 'obj_' + Date.now(),
                label: newObj.label || 'Object',
                color: newObj.color || '#00ff00',
                conf: newObj.conf,
                cx: newObj.x, cy: newObj.y,
                cw: newObj.w || 25, ch: newObj.h || 40,
                tx: newObj.x, ty: newObj.y,
                tw: newObj.w || 25, th: newObj.h || 40
            });
        }
    });
    
    const newIds = objects.map(o => o.id);
    animatedObjects = animatedObjects.filter(o => newIds.includes(o.id));
}

animate();

setInterval(() => {
    document.getElementById('timeDisplay').textContent = new Date().toLocaleTimeString('en-US', {hour12: false});
}, 1000);

function setCmd(c) { document.getElementById('cmdInput').value = c; }

async function startTracking() {
    const cmd = document.getElementById('cmdInput').value;
    await fetch('/api/task', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task: cmd})});
    await fetch('/api/start', {method: 'POST'});
    
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('statusText').textContent = 'TRACKING';
    tracking = true;
    
    refreshInterval = setInterval(refresh, 800);
    refresh();
}

async function stopTracking() {
    await fetch('/api/stop', {method: 'POST'});
    
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('statusText').textContent = 'STOPPED';
    tracking = false;
    animatedObjects = [];
    
    clearInterval(refreshInterval);
}

async function scanNow() {
    const cmd = document.getElementById('cmdInput').value;
    await fetch('/api/task', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task: cmd})});
    
    document.getElementById('analysisText').textContent = 'Scanning...';
    
    const r = await fetch('/api/scan', {method: 'POST'});
    const d = await r.json();
    
    if (d.analysis) {
        updateUI(d.analysis);
        updateTracking(d.analysis.tracked_objects || []);
        if (d.analysis.alert) {
            showAlertBanner(d.analysis.alert_message || 'Detection!');
        }
    }
    refresh();
}

function showAlertBanner(msg) {
    const banner = document.getElementById('alertBanner');
    banner.textContent = msg;
    banner.classList.add('show');
    setTimeout(() => banner.classList.remove('show'), 3000);
}

function updateLeftAlerts(alerts) {
    const container = document.getElementById('leftAlerts');
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = alerts.slice(0, 5).map(a => 
        '<div class="left-alert"><div class="left-alert-icon">!</div><div class="left-alert-content"><div class="left-alert-msg">' + a.message + '</div><div class="left-alert-time">' + a.time + '</div></div></div>'
    ).join('');
}

async function refresh() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        
        document.getElementById('hudScans').textContent = d.stats.scans;
        document.getElementById('hudAlerts').textContent = d.stats.alerts;
        document.getElementById('hudPeople').textContent = d.stats.humans;
        document.getElementById('statScans').textContent = d.stats.scans;
        document.getElementById('statAlerts').textContent = d.stats.alerts;
        document.getElementById('statPeople').textContent = d.stats.humans;
        
        if (d.last_analysis) {
            updateUI(d.last_analysis);
            updateTracking(d.last_analysis.tracked_objects || []);
            
            const tracked = d.last_analysis.tracked_objects || [];
            document.getElementById('hudTrack').textContent = tracked.length;
            document.getElementById('statTrack').textContent = tracked.length;
            
            if (d.stats.alerts > alertCount) {
                alertCount = d.stats.alerts;
                showAlertBanner(d.last_analysis.alert_message || 'Alert!');
            }
        }
        
        updateLeftAlerts(d.alerts);
        
        if (d.alerts && d.alerts.length > 0) {
            document.getElementById('alertsList').innerHTML = d.alerts.slice(0, 8).map(a => 
                '<div class="alert-item"><div class="alert-icon info">!</div><div class="alert-content"><div class="alert-msg">' + a.message + '</div><div class="alert-time">' + a.time + '</div></div></div>'
            ).join('');
        }
    } catch (e) {
        console.error(e);
    }
}

function updateUI(data) {
    document.getElementById('analysisText').textContent = data.scene || 'No analysis';
    
    const tracked = data.tracked_objects || [];
    const all = data.all_objects || [];
    const trackedLabels = tracked.map(t => (t.label || '').toLowerCase());
    
    let html = '';
    tracked.forEach(o => {
        html += '<span class="obj-pill tracked">' + (o.label || o.name) + '</span>';
    });
    all.forEach(name => {
        if (!trackedLabels.includes(name.toLowerCase())) {
            html += '<span class="obj-pill other">' + name + '</span>';
        }
    });
    
    document.getElementById('objectsGrid').innerHTML = html || '<span class="obj-pill other">None</span>';
}

fetch('/api/status').then(r => r.json()).then(d => {
    alertCount = d.stats.alerts;
    if (d.monitoring) {
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        document.getElementById('statusText').textContent = 'TRACKING';
        tracking = true;
        refreshInterval = setInterval(refresh, 800);
        refresh();
    }
});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return DASHBOARD


@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/start")
async def api_start():
    global monitoring_active, monitoring_thread
    if not monitoring_active:
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
    return {"ok": True}


@app.post("/api/stop")
async def api_stop():
    global monitoring_active
    monitoring_active = False
    return {"ok": True}


@app.post("/api/scan")
async def api_scan():
    global last_analysis, stats, detected_objects, alerts_history
    frame = capture_frame()
    if frame:
        stats["scans"] += 1
        result = analyze_frame(frame, current_task)
        result["time"] = datetime.now().strftime('%H:%M:%S')
        result["timestamp"] = time.time()
        last_analysis = result
        stats["humans"] = result.get("people_count", 0)
        detected_objects = result.get("tracked_objects", [])
        
        if result.get("alert", False):
            stats["alerts"] += 1
            alert = {
                "id": stats["alerts"],
                "time": result["time"],
                "type": result.get("alert_type", "info"),
                "message": result.get("alert_message", "Detection alert"),
                "objects": len(detected_objects)
            }
            alerts_history.insert(0, alert)
            print(f"ALERT: {alert['message']}")
        
        return {"analysis": result}
    return {"error": "No frame"}


@app.post("/api/task")
async def api_task(request: Request):
    global current_task
    data = await request.json()
    current_task = data.get("task", current_task)
    return {"ok": True}


@app.get("/api/status")
async def api_status():
    return {
        "monitoring": monitoring_active,
        "stats": stats,
        "last_analysis": last_analysis,
        "alerts": alerts_history[:20]
    }


if __name__ == "__main__":
    print("\n" + "="*50)
    print("   SENTINEL AI - Real-Time Tracking")
    print("="*50)
    print("   Dashboard: http://localhost:8888")
    print("   Model: Gemini 2.5 Flash")
    print("   - Fast 1 second scans")
    print("   - No lag, smooth tracking")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8888)
