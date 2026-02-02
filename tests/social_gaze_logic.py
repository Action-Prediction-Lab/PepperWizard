import unittest
import time
from pepper_wizard.perception.interpreter import PerceptionInterpreter
from pepper_wizard.core.models import Detection, BBox

class TestPerceptionInterpreter(unittest.TestCase):
    def setUp(self):
        self.interpreter = PerceptionInterpreter(width=320, height=240)

    def test_interpret_person_bias(self):
        """Verify that person detections using YOLO are biased towards the head."""
        raw_data = [
            {
                "class": "person",
                "confidence": 0.9,
                "bbox": [100, 100, 200, 300] # x1, y1, x2, y2 -> height = 200
            }
        ]
        target_label = "person"
        timestamp = time.time()
        
        detection = self.interpreter.interpret(raw_data, target_label, timestamp)
        
        self.assertIsNotNone(detection)
        self.assertEqual(detection.label, "person")
        
        # Original center would be y=200
        # Biased center should be y1 + 0.2*h = 100 + 0.2*200 = 140
        center = detection.bbox.center
        self.assertEqual(center.y, 140)
        self.assertEqual(center.x, 150)
        
        # Check BBox dimensions
        # Biased BBox is y1 to y1 + 0.4*h = 100 to 180
        self.assertEqual(detection.bbox.ymin, 100)
        self.assertEqual(detection.bbox.ymax, 180)

    def test_interpret_non_person_no_bias(self):
        """Verify that non-person detections have no bias."""
        raw_data = [
            {
                "class": "chair",
                "confidence": 0.8,
                "bbox": [50, 50, 150, 150] # center (100, 100)
            }
        ]
        target_label = "chair"
        timestamp = time.time()
        
        detection = self.interpreter.interpret(raw_data, target_label, timestamp)
        
        self.assertIsNotNone(detection)
        center = detection.bbox.center
        self.assertEqual(center.y, 100)
        self.assertEqual(center.x, 100)

    def test_mediapipe_primacy(self):
        """Verify that MediaPipe markers are still used for people if available."""
        raw_data = {
            "pose_landmarks": [
                {"x": 0.5, "y": 0.2, "z": 0.0, "visibility": 1.0} # Nose
            ],
            "detections": [] # YOLO empty
        }
        target_label = "person"
        timestamp = time.time()
        
        detection = self.interpreter.interpret(raw_data, target_label, timestamp)
        
        self.assertIsNotNone(detection)
        # Mediapipe is 0.5 * 320 = 160, 0.2 * 240 = 48
        center = detection.bbox.center
        self.assertEqual(center.x, 160)
        self.assertEqual(center.y, 48)

if __name__ == "__main__":
    unittest.main()
