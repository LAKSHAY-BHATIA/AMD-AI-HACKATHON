# pip install fastapi uvicorn opencv-python websockets
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
import cv2
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path

app = FastAPI(title="Factory Multimodal Ingestion API")

# --- Config ---
VIDEO_SOURCE = "factory.mp4"  # falls back to webcam 0 if not found
FPS = 30

def get_video_cap():
    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    return cap

# ========== 1. Video Stream API ==========
# RTSP / MP4 / Webcam - 30 FPS
@app.get("/api/video/stream")
async def video_stream():
    """MJPEG stream - open in browser at http://localhost:8001/api/video/stream"""
    cap = get_video_cap()
    
    async def generate():
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            await asyncio.sleep(1/FPS)
    
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/api/video/ws")
async def video_ws(websocket: WebSocket):
    await websocket.accept()
    cap = get_video_cap()
    frame_id = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        await websocket.send_bytes(buffer.tobytes())
        frame_id += 1
        await asyncio.sleep(1/FPS)

# ========== 2. Telemetry API ==========
# MQTT / OPC-UA / REST - Vibration, Temp, RPM, Pressure
@app.get("/api/telemetry/poll")
async def telemetry_poll():
    """REST poll - for quick testing"""
    return {
        "timestamp": datetime.now().isoformat(),
        "machine_id": random.choice(["Line_1", "Line_2"]),
        "vibration": round(random.uniform(5.0, 10.0), 2),  # >8.0 = alert
        "temperature": round(random.uniform(60, 95), 1),   # >90 = alert
        "rpm": random.randint(1400, 1600),
        "pressure": round(random.uniform(2.0, 3.5), 2)
    }

@app.websocket("/api/telemetry/stream")
async def telemetry_stream(websocket: WebSocket):
    """6 Hz telemetry stream - connect your TelemetryAgent here"""
    await websocket.accept()
    while True:
        data = {
            "type": "telemetry",
            "timestamp": datetime.now().isoformat(),
            "machine_id": "Line_2",
            "vibration": round(random.uniform(5.0, 10.0), 2),
            "temperature": round(random.uniform(60, 95), 1),
            "rpm": random.randint(1400, 1600),
            "pressure": round(random.uniform(2.0, 3.5), 2)
        }
        await websocket.send_text(json.dumps(data))
        await asyncio.sleep(0.16)  # ~6 Hz

# ========== 3. Logs API ==========
# Machine error codes
ERROR_CODES = ["E101_OVERTEMP", "E203_VIBRATION_HIGH", "E405_BELT_SLIP", "OK", "OK", "OK"]

@app.websocket("/api/logs/stream")
async def logs_stream(websocket: WebSocket):
    await websocket.accept()
    while True:
        log = {
            "type": "log",
            "timestamp": datetime.now().isoformat(),
            "machine_id": "Line_2",
            "error_code": random.choice(ERROR_CODES),
            "message": "PLC heartbeat"
        }
        await websocket.send_text(json.dumps(log))
        await asyncio.sleep(1.0)

# ========== 4. Merged Multimodal Stream ==========
# One socket with video + telemetry + logs - for your workflow
@app.websocket("/api/multimodal/stream")
async def multimodal_stream(websocket: WebSocket):
    """Single WS that your MAF workflow consumes"""
    await websocket.accept()
    cap = get_video_cap()
    frame_count = 0
    
    while True:
        # video frame as base64? here we just send metadata, 
        # client pulls MJPEG separately for speed
        ret, _ = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        packet = {
            "frame_id": frame_count,
            "timestamp": datetime.now().isoformat(),
            "telemetry": {
                "vibration": round(random.uniform(5.0, 10.0), 2),
                "temperature": round(random.uniform(60, 95), 1),
                "rpm": random.randint(1400, 1600),
                "pressure": round(random.uniform(2.0, 3.5), 2)
            },
            "log": {
                "error_code": random.choice(ERROR_CODES)
            },
            "video_url": "ws://localhost:8001/api/video/ws"
        }
        await websocket.send_text(json.dumps(packet))
        frame_count += 1
        await asyncio.sleep(1/FPS)