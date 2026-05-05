import os
import json
import contextlib
import wave
import subprocess
import re
import math


def extract_timings(scenes: list[dict], audio_path: str) -> list[dict]:
    """
    Uses stable-ts forced alignment to get precise per-scene timestamps.
    Frame numbers use CUMULATIVE ROUNDING to prevent drift from int() truncation.
    """
    FPS = 30
    audio_duration = _get_audio_duration(audio_path)
    print(f"[Timing] Audio duration: {audio_duration:.2f}s")

    full_text = "\n".join(s["script_text"] for s in scenes)

    try:
        import stable_whisper
        print("[Timing] Loading stable-ts model...")
        model = stable_whisper.load_model("base")
        print("[Timing] Force-aligning transcript to audio...")
        result = model.align(
            audio_path, full_text, language="en",
            original_split=True, token_step=200,
        )

        segments = list(result.segments)
        print(f"[Timing] Got {len(segments)} aligned segments for {len(scenes)} scenes")

        if len(segments) == len(scenes):
            timings = _build_timings_from_segments(scenes, segments, audio_duration, FPS)
        else:
            print("[Timing] Segment count mismatch, using segment timestamps with mapping")
            timings = _build_timings_from_words(scenes, result, audio_duration, FPS)

        _print_timings(timings)
        return timings

    except Exception as e:
        print(f"[Timing] stable-ts failed: {e}")
        import traceback
        traceback.print_exc()

    print("[Timing] Using proportional fallback.")
    result = _proportional_timing(scenes, audio_duration, FPS)
    _print_timings(result)
    return result


def _build_timings_from_segments(scenes, segments, audio_duration, FPS):
    """Build timings using 1:1 segment mapping with cumulative frame rounding."""
    timings = []
    for i, scene in enumerate(scenes):
        start_time = segments[i].start
        if i < len(scenes) - 1:
            end_time = segments[i + 1].start
        else:
            end_time = audio_duration
        duration = max(end_time - start_time, 0.5)

        # Use cumulative rounding: start_frame = round(start_time * FPS)
        # This prevents frame loss from int() truncation
        start_frame = round(start_time * FPS)
        if i < len(scenes) - 1:
            next_start_frame = round(segments[i + 1].start * FPS)
        else:
            next_start_frame = round(audio_duration * FPS)
        duration_frames = max(next_start_frame - start_frame, 1)

        timings.append({
            **scene,
            "start": round(start_time, 3),
            "duration": round(duration, 3),
            "start_frame": start_frame,
            "duration_frames": duration_frames,
        })
    return timings


def _build_timings_from_words(scenes, result, audio_duration, FPS):
    """Fallback: use word timestamps when segment count doesn't match."""
    all_words = []
    for seg in result.segments:
        for w in seg.words:
            all_words.append({"word": w.word, "start": w.start, "end": w.end})

    # Build char→word mapping
    char_to_word = []
    for j, w in enumerate(all_words):
        txt = w["word"].strip()
        if char_to_word:
            char_to_word.append(j)
        for _ in txt:
            char_to_word.append(j)

    full_text = " ".join(s["script_text"] for s in scenes)
    pos = 0
    scene_char_starts = []
    for s in scenes:
        scene_char_starts.append(pos)
        pos += len(s["script_text"]) + 1

    total_chars = len(char_to_word)
    timings = []
    for i, scene in enumerate(scenes):
        cp = min(scene_char_starts[i], total_chars - 1)
        widx = char_to_word[cp]
        start_time = all_words[widx]["start"]

        if i < len(scenes) - 1:
            ncp = min(scene_char_starts[i + 1], total_chars - 1)
            nwidx = char_to_word[ncp]
            end_time = all_words[nwidx]["start"]
        else:
            end_time = audio_duration

        duration = max(end_time - start_time, 0.5)
        start_frame = round(start_time * FPS)
        if i < len(scenes) - 1:
            ncp2 = min(scene_char_starts[i + 1], total_chars - 1)
            nwidx2 = char_to_word[ncp2]
            next_start = all_words[nwidx2]["start"]
            next_start_frame = round(next_start * FPS)
        else:
            next_start_frame = round(audio_duration * FPS)
        duration_frames = max(next_start_frame - start_frame, 1)

        timings.append({
            **scene,
            "start": round(start_time, 3),
            "duration": round(duration, 3),
            "start_frame": start_frame,
            "duration_frames": duration_frames,
        })
    return timings


def _get_audio_duration(audio_path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True
        )
        dur = float(result.stdout.strip())
        if dur > 0:
            return dur
    except Exception:
        pass
    try:
        with contextlib.closing(wave.open(audio_path, 'r')) as f:
            return f.getnframes() / float(f.getframerate())
    except Exception:
        pass
    return 60.0


def _proportional_timing(scenes, audio_duration, FPS):
    total_chars = sum(len(s["script_text"]) for s in scenes)
    timings = []
    current = 0.0
    for i, scene in enumerate(scenes):
        dur = (len(scene["script_text"]) / total_chars) * audio_duration
        start_frame = round(current * FPS)
        next_start = current + dur
        if i < len(scenes) - 1:
            next_frame = round(next_start * FPS)
        else:
            next_frame = round(audio_duration * FPS)
        duration_frames = max(next_frame - start_frame, 1)

        timings.append({
            **scene,
            "start": round(current, 3),
            "duration": round(dur, 3),
            "start_frame": start_frame,
            "duration_frames": duration_frames,
        })
        current += dur
    return timings


def _print_timings(timings):
    total_frames = sum(t["duration_frames"] for t in timings)
    for t in timings:
        print(f"  Scene {t['scene_id']}: {t['start']:.2f}s - {t['start'] + t['duration']:.2f}s "
              f"({t['duration']:.2f}s) [{t['script_text'][:50]}...]")
    print(f"[Timing] Total frames: {total_frames}")
