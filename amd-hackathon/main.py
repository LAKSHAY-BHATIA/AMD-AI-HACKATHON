# main.py
import asyncio
import cv2
import json
import websockets
import threading
import argparse
import sys
from pathlib import Path

from core.preprocessor import preprocess_packet
from workflows.factory_workflow import run_factory_cycle

# --- Dev UI ---
def _start_devui():
    from agent_framework.devui import serve
    from workflows.factory_workflow import factory_workflow
    # If your agents live in agents/<name>/<name>.py with `agent = Agent(...)`
    # use:
    # from agents.defect_analysis_agent import agent as defect_agent
    # from agents.telemetry_agent.telemetry_agent import agent as telemetry_agent
    # from agents.safety_agent.safety_agent import agent as safety_agent
    # from agents.orchestrator_agent.orchestrator_agent import agent as orchestrator_agent
    # from agents.kpi_tracker_agent.kpi_tracker_agent import agent as kpi_tracker_agent

    # If you added the __init__.py re-exports, this works:
   
    from agents.defect_analysis_agent.defect_analysis_agent import agent as defect_agent
    from agents.telemetry_agent.telemetry_agent import agent as telemetry_agent
    from agents.safety_agent.safety_agent import agent as safety_agent
    from agents.orchestrator_agent.orchestrator_agent import orchestrator_agent as orchestrator_agent

    from agents.kpi_tracker_agent import agent as kpi_tracker_agent
    

    entities = [
        defect_agent,
        telemetry_agent,
        safety_agent,
        orchestrator_agent,
        kpi_tracker_agent,
        factory_workflow,
    ]
    entities = [e for e in entities if e is not None]
    
    print("workflow:", factory_workflow)

    serve(
        entities=entities,
        host="0.0.0.0",
        auth_token="lakshay",
        port=8080,
    )

# --- Telemetry with auto-reconnect ---
TELEMETRY_URL = "ws://localhost:8001/api/telemetry/stream"
VIDEO_URL = "http://localhost:8001/api/video/stream"
VIDEO_FALLBACK = "factory.mp4"

async def telemetry_reader(queue: asyncio.Queue, url: str):
    """Keeps a live telemetry dict in queue, reconnects on drop"""
    while True:
        try:
            async with websockets.connect(url, open_timeout=5) as ws:
                async for msg in ws:
                    try:
                        await queue.put(json.loads(msg))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            await asyncio.sleep(1.0)
            continue

async def factory_data_stream(video_source: str = VIDEO_URL, telemetry_url: str = TELEMETRY_URL):
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened() and Path(VIDEO_FALLBACK).exists():
        print(f"Video stream {video_source} unavailable, using {VIDEO_FALLBACK}")
        cap = cv2.VideoCapture(VIDEO_FALLBACK)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
        print("Using webcam as fallback")

    tel_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
    asyncio.create_task(telemetry_reader(tel_queue, telemetry_url))

    last_tel = {"vibration": 6.0, "temperature": 70.0, "machine_id": "Line_2", "timestamp": ""}
    frame_id = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            while not tel_queue.empty():
                try:
                    last_tel = tel_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            p = preprocess_packet(
                {"frame": frame, "telemetry": last_tel, "timestamp": last_tel.get("timestamp", "")},
                frame_id=frame_id
            )
            frame_id += 1
            yield p
            await asyncio.sleep(1/30)
    finally:
        cap.release()

# --- Main loop ---
async def main(video_source: str, telemetry_url: str):
    stats = {"normal": 0, "quality_defect": 0, "safety_violation": 0, "critical_maintenance": 0}
    try:
        async for p in factory_data_stream(video_source, telemetry_url):
            decision, action = await run_factory_cycle(p)
            stats[decision] = stats.get(decision, 0) + 1
            print(p)
            print(f"[{p.frame_id:05d}] {p.machine_id} | vib={p.input_vibration:.1f} temp={p.input_temp:.1f} | {decision} -> {action}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n--- Run summary ---")
        for k, v in stats.items():
            print(f" {k}: {v}")
        print("KPIs saved to factory_kpis.xlsx")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MULTIMODAL_004 Factory AI runner")
    parser.add_argument("--video", default=VIDEO_URL, help="Video source URL or file")
    parser.add_argument("--telemetry", default=TELEMETRY_URL, help="Telemetry websocket URL")
    parser.add_argument("--no-devui", action="store_true", help="Disable Dev UI")
    args = parser.parse_args()

    if not args.no_devui:
        threading.Thread(target=_start_devui, daemon=True).start()
        print("Dev UI: http://localhost:8080")

    try:
        asyncio.run(main(args.video, args.telemetry))
    except KeyboardInterrupt:
        print("\nShutdown requested")
        sys.exit(0)