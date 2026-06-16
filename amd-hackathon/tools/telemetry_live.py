# tools/telemetry_live.py
import asyncio
import json
from typing import Dict, Any

TELEMETRY_REST = "http://localhost:8001/api/telemetry/poll"
TELEMETRY_WS = "ws://localhost:8001/api/multimodal/stream"
VIDEO_URL = "http://localhost:8001/api/video/stream"

_latest: Dict[str, Any] = {
    "vibration": 0.0,
    "temperature": 0.0,
    "rpm": 0,
    "pressure": 0.0,
    "error_code": "OK",
    "machine_id": "Line_2"
}
_lock = asyncio.Lock()
_listener_running = False

async def update_telemetry(vibration, temperature, rpm=0, pressure=0.0, error_code="OK"):
    async with _lock:
        _latest["vibration"] = float(vibration)
        _latest["temperature"] = float(temperature)
        _latest["rpm"] = rpm
        _latest["pressure"] = pressure
        _latest["error_code"] = error_code

async def get_live_telemetry(machine_id: str = "Line_2") -> str:
    """Tool for agents. Returns live factory snapshot as JSON string."""
    # try a quick REST poll first, so Dev UI Run is instant even if WS isn't running
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(TELEMETRY_REST, timeout=1.0)
            if r.status_code == 200:
                d = r.json()
                await update_telemetry(
                    d.get("vibration", 0),
                    d.get("temperature", 0),
                    d.get("rpm", 0),
                    d.get("pressure", 0),
                    "OK"
                )
    except Exception:
        pass

    async with _lock:
        d = _latest.copy()
    d["machine_id"] = machine_id
    return json.dumps(d)

async def get_live_video_frame_url() -> str:
    return VIDEO_URL

async def start_multimodal_listener():
    """Background task: ws://localhost:8001/api/multimodal/stream -> cache"""
    global _listener_running
    if _listener_running:
        return
    _listener_running = True
    import websockets
    while True:
        try:
            async with websockets.connect(TELEMETRY_WS) as ws:
                async for msg in ws:
                    pkt = json.loads(msg)
                    tel = pkt.get("telemetry", {})
                    log = pkt.get("log", {})
                    await update_telemetry(
                        tel.get("vibration", 0),
                        tel.get("temperature", 0),
                        tel.get("rpm", 0),
                        tel.get("pressure", 0),
                        log.get("error_code", "OK")
                    )
        except Exception:
            await asyncio.sleep(2.0)