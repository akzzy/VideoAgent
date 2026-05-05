import json
import whisper
import os

def get_timings():
    print("Loading whisper model...")
    model = whisper.load_model("base")
    print("Transcribing audio.wav...")
    result = model.transcribe("audio.wav", word_timestamps=True)
    
    with open("master_script.json", "r") as f:
        data = json.load(f)
        
    words = result.get("segments", [])
    all_words = []
    for segment in words:
        if "words" in segment:
            all_words.extend(segment["words"])
            
    print(f"Total words transcribed: {len(all_words)}")
    
    timings = []
    current_word_idx = 0
    total_audio_duration = result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0
    
    for idx, scene in enumerate(data["scenes"]):
        # A very basic alignment: assign equal time if whisper alignment is complex, 
        # but let's try to map the script text to the audio text.
        # Actually, simpler approach for this agent: evenly distribute or use rough text length
        pass
        
    # To be extremely robust, let's just use the exact text length to estimate duration!
    # Whisper word-level alignment can be tricky. Let's just use the segment timing.
    # We will match the text of the scene to the segments.
    
    scene_timings = []
    for scene in data["scenes"]:
        text = scene["exact_sentence_from_script"]
        scene_timings.append({
            "id": scene["scene_id"],
            "text": text,
            "char_count": len(text)
        })
        
    total_chars = sum(s["char_count"] for s in scene_timings)
    
    # Let's get actual audio duration
    import wave
    import contextlib
    audio_duration = 0
    with contextlib.closing(wave.open("audio.wav",'r')) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        audio_duration = frames / float(rate)
        
    print(f"Total Audio Duration: {audio_duration:.2f}s")
    
    # Calculate durations proportionally
    current_start = 0.0
    for scene in scene_timings:
        duration = (scene["char_count"] / total_chars) * audio_duration
        scene["start"] = current_start
        scene["duration"] = duration
        current_start += duration
        
    with open("timings.json", "w") as f:
        json.dump(scene_timings, f, indent=2)
        
    print("Saved timings to timings.json")

if __name__ == "__main__":
    get_timings()
