import asyncio
import json
import websockets
import cv2

async def factory_data_stream():
    # 1. Video via OpenCV - 30 FPS, zero latency
    cap = cv2.VideoCapture("http://localhost:8001/api/video/stream")
    if not cap.isOpened():
        cap = cv2.VideoCapture("factory.mp4")
    
    # 2. Telemetry via WebSocket
    async with websockets.connect("ws://localhost:8001/api/telemetry/stream") as ws:
        while True:
            # yield video frame
            ret, frame = cap.read()
            if ret:
                yield {"type": "vision", "timestamp": None, "data": frame}
            
            # yield telemetry - non-blocking
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                tel = json.loads(msg)
                yield {"type": "telemetry", "timestamp": tel["timestamp"], "data": tel}
            except asyncio.TimeoutError:
                pass
            
            await asyncio.sleep(1/30)