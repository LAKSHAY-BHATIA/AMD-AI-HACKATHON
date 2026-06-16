from ultralytics import YOLO
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict
from collections import deque

# --- Model ---
# COCO yolov8n has no helmet/gloves. Use a PPE model to get real alerts:
# e.g. YOLO("keremberke/yolov8n-hard-hat-detection.pt") or "hardhat_best.pt"
try:
    YOLO_MODEL = YOLO("hardhat_best.pt")
    MODEL_NAME = "ppe"
except Exception:
    YOLO_MODEL = YOLO("yolov8n.pt")
    MODEL_NAME = "coco"

# PPE class maps, normalized to lowercase
HELMET_POS = {"helmet", "hard_hat", "hardhat", "safety_helmet"}
HELMET_NEG = {"no_helmet", "no_hardhat", "no_hard_hat"}
GLOVES_POS = {"gloves"}
GLOVES_NEG = {"no_gloves"}

# Simple temporal smoothing to kill flicker, 3-frame majority
_history = deque(maxlen=3)

def detect_objects(frame: np.ndarray, conf: float = 0.4) -> List[str]:
    if frame is None:
        return []
    r = YOLO_MODEL(frame, verbose=False, conf=conf)[0]
    names = [YOLO_MODEL.names[int(c)].lower() for c in r.boxes.cls]
    return names

def check_ppe(detected: List[str], workstation_zone: bool = True) -> Dict:
    d = set(detected)
    has_person = "person" in d
    has_helmet = len(d & HELMET_POS) > 0
    has_gloves = len(d & GLOVES_POS) > 0
    no_helmet = len(d & HELMET_NEG) > 0
    no_gloves = len(d & GLOVES_NEG) > 0

    # Only flag if a negative class is positively detected.
    # With base coco model this will never fire, which is correct.
    violation = False
    reason = "clear"

    if has_person and workstation_zone:
        if no_helmet:
            violation = True
            reason = "no_helmet"
        elif no_gloves:
            violation = True
            reason = "no_gloves"
        # Do NOT infer missing PPE from absence when using COCO
        # elif MODEL_NAME == "ppe" and not has_helmet:
        # uncomment this block only after you have a real PPE model
        # violation = True
        # reason = "missing_helmet"

    # temporal smoothing
    _history.append(violation)
    violation_smooth = sum(_history) >= 2 # 2 of last 3 frames

    return {
        "person_detected": has_person,
        "helmet_detected": has_helmet,
        "gloves_detected": has_gloves,
        "ppe_violation": violation_smooth,
        "ppe_reason": reason if violation_smooth else "clear",
        "model": MODEL_NAME,
        "workstation_zone": workstation_zone,
    }

@dataclass
class PreprocessedPacket:
    timestamp: str
    frame_id: int
    input_vibration: float
    input_temp: float
    input_detected_objects: str
    detected_objects: List[str]
    machine_id: str = "Line_2"
    # new PPE fields, safe defaults so old agents still work
    ppe_violation: bool = False
    ppe_reason: str = "clear"
    person_detected: bool = False
    helmet_detected: bool = False
    gloves_detected: bool = False

def preprocess_packet(raw: dict, frame_id: int = 0, workstation_zone: bool = True) -> PreprocessedPacket:
    frame = raw.get("frame")
    tel = raw.get("telemetry", {})
    detected = detect_objects(frame)
    ppe = check_ppe(detected, workstation_zone=workstation_zone)

    return PreprocessedPacket(
        timestamp=raw.get("timestamp", ""),
        frame_id=frame_id,
        input_vibration=tel.get("vibration", 0.0),
        input_temp=tel.get("temperature", 0.0),
        input_detected_objects=",".join(detected) if detected else "none",
        detected_objects=detected,
        machine_id=tel.get("machine_id", "Line_2"),
        ppe_violation=ppe["ppe_violation"],
        ppe_reason=ppe["ppe_reason"],
        person_detected=ppe["person_detected"],
        helmet_detected=ppe["helmet_detected"],
        gloves_detected=ppe["gloves_detected"],
    )