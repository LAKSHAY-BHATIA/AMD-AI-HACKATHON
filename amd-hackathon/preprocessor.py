# pip install ultralytics opencv-python numpy
import cv2
import numpy as np
from ultralytics import YOLO
from datetime import datetime
from typing import Dict, Any, AsyncGenerator

class FactoryPreprocessor:
    def __init__(
        self,
        model_path: str = "yolov8n.pt", # swap to "best.pt" for hard-hat model
        conf: float = 0.35,
        imgsz: int = 640,
    ):
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz

        # Telemetry normalization ranges - for LLM stability
        self.norm_ranges = {
            "vibration": (0.0, 12.0), # mm/s
            "temperature": (0.0, 120.0), # °C
            "rpm": (0.0, 2000.0),
            "pressure": (0.0, 5.0),
        }

    def _normalize(self, key: str, val: float) -> float:
        lo, hi = self.norm_ranges.get(key, (0, 1))
        return max(0.0, min(1.0, (val - lo) / (hi - lo)))

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """YOLOv8n - returns detected objects for agents"""
        results = self.model(frame, confHere is the Preprocessor that sits right between your `factory_data_stream()` and the 3 analysis agents.

It takes the raw `{frame, telemetry, timestamp}` from the Ingestion API, runs YOLOv8n, normalizes the sensor values, and emits a clean packet that your `DefectAnalysisAgent / TelemetryAgent / SafetyAgent` can consume directly.

### `core/preprocessor.py`

```python
# pip install ultralytics opencv-python numpy
from ultralytics import YOLO
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Dict

# --- Load once at startup ---
# For hackathon: yolov8n.pt works out of the box
# For hard-hat detection: swap to "best.pt" from Roboflow Hard Hat dataset
YOLO_MODEL = YOLO("yolov8n.pt")
# YOLO_MODEL = YOLO("models/hardhat_best.pt")

# Telemetry normalization ranges - adjust to your PLC
TELEMETRY_RANGES = {
    "vibration": {"min": 0.0, "max": 12.0}, # mm/s, alert > 8.0
    "temperature": {"min": 20.0, "max": 120.0}, # °C, alert > 90
    "rpm": {"min": 0, "max": 2000},
    "pressure": {"min": 0.0, "max": 5.0},
}

def normalize_telemetry(raw: dict) -> dict:
    """Min-max normalize, keep raw values too for KPI logging"""
    norm = {}
    for k, cfg in TELEMETRY_RANGES.items():
        if k in raw:
            v = float(raw[k])
            n = (v - cfg["min"]) / (cfg["max"] - cfg["min"])
            norm[f"{k}_norm"] = np.clip(n, 0, 1)
            norm[k] = v # keep raw
    return norm

def detect_objects(frame: np.ndarray, conf: float = 0.4) -> List[str]:
    """YOLOv8n inference"""
    results = YOLO_MODEL(frame, verbose=False, conf=conf)
    names = YOLO_MODEL.names
    detected = []
    for r in results:
        for c in r.boxes.cls:
            detected.append(names[int(c)])
    return detected

def check_safety(detected: List[str]) -> Dict[str, int]:
    """Simple safety rules for SafetyAgent input"""
    # for a real hard-hat model, look for 'no_helmet', 'no_gloves'
    # for base yolov8n, we just flag person presence
    has_person = "person" in detected
    # stub: assume violation if person detected - replace with real model
    return {
        "person_detected": int(has_person),
        "safety_violation": 0 # set to 1 by SafetyAgent LLM if needed
    }

@dataclass
class PreprocessedPacket:
    timestamp: str
    frame_id: int
    # raw inputs - for KPI Excel logging
    input_vibration: float
    input_temp: float
    input_detected_objects: str
    # normalized - for agents
    telemetry_norm: dict
    detected_objects: List[str]
    safety_flags: dict
    machine_id: str = "Line_2"

def preprocess_packet(raw_packet: dict, frame_id: int = 0) -> PreprocessedPacket:
    """Takes one {frame, telemetry, timestamp} from factory_data_stream()"""
    frame = raw_packet.get("frame")
    tel_raw = raw_packet.get("telemetry", {})
    ts = raw_packet.get("timestamp")

    # 1. Vision
    detected = detect_objects(frame) if frame is not None else []
    safety_flags = check_safety(detected)

    # 2. Telemetry
    tel_norm = normalize_telemetry(tel_raw)

    return PreprocessedPacket(
        timestamp=ts,
        frame_id=frame_id,
        input_vibration=tel_raw.get("vibration", 0.0),
        input_temp=tel_raw.get("temperature", 0.0),
        input_detected_objects=",".join(detected) if detected else "none",
        telemetry_norm=tel_norm,
        detected_objects=detected,
        safety_flags=safety_flags,
        machine_id=tel_raw.get("machine_id", "Line_2")
    )