#!/usr/bin/env python3
"""Manual end-to-end smoke test for the recording subsystem.

Runs against the live stack. Records for N seconds, then ffprobes the resulting
MKV and prints sync diagnostics from the sidecar.

Usage (from within pepper-wizard container):
    python3 tools/record_smoke_test.py
    python3 tools/record_smoke_test.py --duration 30 --session-id smoke
"""
import argparse
import json
import os
import subprocess
import sys
import time

from pepper_wizard.config import load_recording_config
from pepper_wizard.recording import Recorder


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--session-id", default="smoke")
    p.add_argument("--video-address", default="tcp://localhost:5559")
    p.add_argument("--audio-address", default="tcp://localhost:5563")
    p.add_argument("--clock-sync-url", default="http://localhost:5000/time")
    p.add_argument("--config", default="pepper_wizard/config/recording.json")
    args = p.parse_args()

    cfg = load_recording_config(args.config)
    print(f"Config: {cfg}")

    rec = Recorder(
        config=cfg,
        session_id=args.session_id,
        video_address=args.video_address,
        audio_address=args.audio_address,
        clock_sync_url=args.clock_sync_url,
    )
    print(f"Starting recording for {args.duration}s...")
    rec.start()
    time.sleep(args.duration)
    paths = rec.stop()

    print("\n=== Files written ===")
    for k, v in paths.items():
        size = os.path.getsize(v) if os.path.exists(v) else 0
        print(f"  {k}: {v} ({size} bytes)")

    print("\n=== ffprobe ===")
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams",
             "-of", "json", paths["mkv"]],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            info = json.loads(r.stdout)
            for s in info.get("streams", []):
                print(f"  stream {s['index']}: {s['codec_type']} / {s['codec_name']} "
                      f"duration={s.get('duration', '?')}")
            print(f"  format duration: {info.get('format', {}).get('duration', '?')}")
        else:
            print(f"  ffprobe failed: {r.stderr}")
    except FileNotFoundError:
        print("  ffprobe not installed")

    print("\n=== Sidecar summary ===")
    with open(paths["jsonl"]) as f:
        lines = [json.loads(l) for l in f if l.strip()]
    header = lines[0]
    print(f"  recording_start_utc_ns: {header['recording_start_utc_ns']}")
    print(f"  clock_sync: {header.get('clock_sync')}")
    counts = {}
    for l in lines[1:]:
        counts[l.get("type", "?")] = counts.get(l.get("type", "?"), 0) + 1
    print(f"  records: {counts}")
    if counts.get("video", 0) > 0 and counts.get("audio", 0) > 0:
        print("  PASS: both streams captured")
        return 0
    print("  FAIL: missing stream(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
