from typing import Optional, List, Dict, Any
from ..core.models import Detection, BBox

class PerceptionInterpreter:
    """
    Decouples raw perception data from the Orchestrator.
    Handles backend-specific data structures (Mediapipe, YOLO) 
    and returns a normalized Detection object.
    """
    def __init__(self, width: int = 320, height: int = 240):
        self.width = width
        self.height = height

    def interpret(self, raw_data: Any, target_label: str, timestamp: float, source_angles: Optional[tuple] = None) -> Optional[Detection]:
        """
        Interprets raw perception data and returns the best matching Detection.
        """
        if not target_label:
            return None
            
        # 1. Mediapipe Primacy (Person/Face)
        is_person_target = target_label.lower() in ["person", "human", "face", "man", "woman"]
        
        if is_person_target and isinstance(raw_data, dict) and "pose_landmarks" in raw_data:
            pose = raw_data.get("pose_landmarks")
            if pose and len(pose) > 0:
                nose = pose[0]
                # Mediapipe is 0-1 normalized, convert to pixels
                nx = nose["x"] * self.width
                ny = nose["y"] * self.height
                # Create a point-bbox [x, y, x, y]
                return Detection(
                    label=target_label,
                    confidence=1.0, # Landmarks are usually high confidence
                    bbox=BBox(nx, ny, nx, ny),
                    timestamp=timestamp,
                    source_angles=source_angles
                )

        # 2. YOLO / Detection Fallback
        detections_list = []
        if isinstance(raw_data, list):
            detections_list = raw_data
        elif isinstance(raw_data, dict) and "detections" in raw_data:
            detections_list = raw_data["detections"]
            
        best_det = None
        max_conf = 0.0
        
        for det in detections_list:
            if det["class"] == target_label and det["confidence"] > 0.25:
                if det["confidence"] > max_conf:
                    max_conf = det["confidence"]
                    best_det = det
        
        if best_det:
            bx = best_det["bbox"]
            
            # Social Bias: If target is a person, bias the center towards the head (Top 20%)
            if is_person_target:
                x1, y1, x2, y2 = bx
                height = y2 - y1
                # Return a virtual BBox that is focused on the top 40% of the body
                # The center of this box will be at target_y = y1 + 0.2 * height (the head)
                return Detection(
                    label=target_label,
                    confidence=best_det["confidence"],
                    bbox=BBox(x1, y1, x2, y1 + (0.4 * height)),
                    timestamp=timestamp,
                    source_angles=source_angles
                )

            return Detection(
                label=target_label,
                confidence=best_det["confidence"],
                bbox=BBox(bx[0], bx[1], bx[2], bx[3]),
                timestamp=timestamp,
                source_angles=source_angles
            )
            
        return None
