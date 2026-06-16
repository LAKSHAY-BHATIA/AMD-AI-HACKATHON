# tools/live_state.py
import asyncio, json
from typing import Dict, Any

VIDEO_URL = "http://localhost:8001/api/video/stream"
TELEMETRY_WS = "ws://localhost:8001/api/multimodal/stream"

_state: Dict[str, Any] = {
    "vibration": 6.0, "temperature": 70.0, "rpm": 1500, "pressure": 2.5,
    "error_code": "OK", "machine_id": "Line_2", "frame_id": 0
}
_lock = asyncio.Lock()

async def update_telemetry(vibration: float, temperature: float, rpm: int = 1500,
                           pressure: float = 2.5, error_code: str = "OK", machine_id: str = "Line_2"):
    async with _lock:
        _state.update(vibration=vibration, temperature=temperature,
                      rpm=rpm, pressure=pressure, error_code=error_code, machine_id=machine_id)

async def get_snapshot() -> Dict[str, Any]:
    async with _lock:
        return dict(_state)

async def start_listener():
    import websockets
    while True:
        try:
            async with websockets.connect(TELEMETRY_WS) as ws:
                async for msg in ws:
                    pkt = json.loads(msg)
                    tel = pkt.get("telemetry", {})
                    await update_telemetry(
                        tel.get("vibration", 6.0), tel.get("temperature", 70.0),
                        tel.get("rpm", 1500), tel.get("pressure", 2.5),
                        pkt.get("log", {}).get("error_code", "OK")
                    )
        except Exception:
            await asyncio.sleep(2)