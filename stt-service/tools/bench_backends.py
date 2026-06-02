"""Backend latency benchmark.

Times Whisper-CPU vs Parakeet-GPU on the same speech, after a
warm-up pass.
Reports cold-load time, warm-call latency, and the resulting transcription
so output drift between engines is visible.

Run inside the stt-service container:
    docker compose run --rm stt-service python3 tools/bench_backends.py
"""
import os
import statistics
import sys
import time
import wave

import numpy as np

# Ensure /app is on sys.path so the script can run from any cwd.
sys.path.insert(0, "/app")

from backends import ParakeetBackend, WhisperBackend


FIXTURE = "/app/tests/fixture_speech_16k.wav"
N_TIMED = 10


def load_audio(path):
    with wave.open(path, "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    audio = pcm.astype(np.float32) / 32768.0
    return audio, len(audio) / 16000.0


def time_backend(label, backend, audio):
    print(f"\n=== {label} ===", flush=True)
    print("warm-up call...", flush=True)
    t0 = time.perf_counter()
    segments, _ = backend.transcribe(audio, beam_size=3, language="en", vad_filter=False)
    text = " ".join(s.text.strip() for s in segments).strip()
    warmup_ms = (time.perf_counter() - t0) * 1000
    print(f"  warm-up: {warmup_ms:.1f} ms")
    print(f"  text:    '{text}'")

    print(f"timed runs (n={N_TIMED})...", flush=True)
    samples = []
    for i in range(N_TIMED):
        t0 = time.perf_counter()
        segments, _ = backend.transcribe(audio, beam_size=3, language="en", vad_filter=False)
        _ = " ".join(s.text.strip() for s in segments).strip()
        samples.append((time.perf_counter() - t0) * 1000)
    return {
        "warmup_ms": warmup_ms,
        "mean_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "stdev_ms": statistics.stdev(samples),
        "text": text,
    }


def main():
    audio, duration_s = load_audio(FIXTURE)
    print(f"Fixture: {FIXTURE}")
    print(f"Duration: {duration_s:.2f} s, {len(audio)} samples @ 16 kHz")

    print("\n--- loading WhisperBackend (CPU, int8, base.en) ---", flush=True)
    t0 = time.perf_counter()
    whisper = WhisperBackend("base.en", device="cpu", compute_type="int8")
    whisper_load_ms = (time.perf_counter() - t0) * 1000
    print(f"  load: {whisper_load_ms:.1f} ms")
    whisper_stats = time_backend("WhisperBackend (CPU int8 base.en)", whisper, audio)
    whisper_stats["load_ms"] = whisper_load_ms

    print("\n--- loading ParakeetBackend (CUDA FP16, parakeet-tdt-0.6b-v2) ---", flush=True)
    t0 = time.perf_counter()
    parakeet = ParakeetBackend("nvidia/parakeet-tdt-0.6b-v2", device="cuda")
    parakeet_load_ms = (time.perf_counter() - t0) * 1000
    print(f"  load: {parakeet_load_ms:.1f} ms")
    parakeet_stats = time_backend("ParakeetBackend (CUDA FP16 0.6b-v2)", parakeet, audio)
    parakeet_stats["load_ms"] = parakeet_load_ms

    audio_ms = duration_s * 1000
    print("\n\n========== RESULTS ==========")
    print(f"Audio length:       {duration_s:.2f} s ({audio_ms:.0f} ms)")
    print(f"Timed runs per engine: {N_TIMED}\n")

    def show(label, s):
        rtf = s["mean_ms"] / audio_ms
        print(f"{label}")
        print(f"  cold load:   {s['load_ms']:7.0f} ms")
        print(f"  warm-up:     {s['warmup_ms']:7.0f} ms")
        print(f"  mean:        {s['mean_ms']:7.1f} ms  (RTF {rtf:.3f}x audio length)")
        print(f"  median:      {s['median_ms']:7.1f} ms")
        print(f"  min / max:   {s['min_ms']:7.1f} / {s['max_ms']:.1f} ms")
        print(f"  stdev:       {s['stdev_ms']:7.1f} ms")
        print(f"  text:        '{s['text']}'\n")

    show("Whisper CPU int8 base.en (baseline)", whisper_stats)
    show("Parakeet CUDA FP16 0.6b-v2 (v2.3.0)", parakeet_stats)

    delta_mean = parakeet_stats["mean_ms"] - whisper_stats["mean_ms"]
    speedup = whisper_stats["mean_ms"] / parakeet_stats["mean_ms"]
    direction = "faster" if delta_mean < 0 else "slower"
    print("--- delta (Parakeet vs Whisper baseline) ---")
    print(f"  mean Δ:      {delta_mean:+.1f} ms  →  {abs(delta_mean):.0f} ms {direction}")
    print(f"  speedup:     {speedup:.2f}x (mean Whisper / mean Parakeet)")
    print(f"  load Δ:      {parakeet_stats['load_ms'] - whisper_stats['load_ms']:+.0f} ms")


if __name__ == "__main__":
    main()
