# PepperWizard Tools

This directory contains tools for visualising, operating and diagnosing with PepperWizard.

## Log Analyzer (`log_analyzer.py`)

A CLI tool to analyse session logs for connectivity issues, system health, and performance stability.

**Usage:**
```bash
docker compose run --rm pepper-wizard python3 -m pepper_wizard.tools.log_analyzer logs/<session_file>.jsonl
```

**Metrics Reported:**
- **Connectivity Health**: Identifies gaps in the message stream (>200ms) and reconnection events.
- **Responsiveness**: Calculates Jitter (standard deviation of command frequency). High jitter (>20ms) indicates network instability.
- **Robot Health**: Tracks battery drain rate and temperature warnings.
- **System Health**: Summarises application errors and warnings.

---

## Proximity Viewer (`proximity_viewer.py`)

A real-time visualiser for the robot's local perception, including Sonar, Laser, and Bumper data.

**Usage:**
```bash
python3 pepper_wizard/tools/proximity_viewer.py <host>
```

**Features:**
- Visualises 360-degree sonar and laser data.
- Displays "HIT" warnings for bumper collisions.
- Shows current head gaze direction.
- Represents persistence through fading.

---

## Vision Viewer (`vision_viewer.py`)

A GUI tool to view the robot's camera feed and overlay perception results (YOLO detections, MediaPipe skeletons).

**Usage:**
```bash
python3 pepper_wizard/tools/vision_viewer.py <host>
```

**Features:**
- **Video Stream**: Low-latency video feed (supports Grey, YUV, RGB).
- **Perception Overlay**: Draws bounding boxes and skeletons from the perception service.
- **Interactive Tracking**: Click on a detected object to command the robot to track the chosen class of objects.
