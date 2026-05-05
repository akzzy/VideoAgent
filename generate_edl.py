import json
import math

def format_tc(frames, fps=24):
    h = frames // (fps * 3600)
    m = (frames // (fps * 60)) % 60
    s = (frames // fps) % 60
    f = frames % fps
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

def main():
    audio_duration = 38.62
    fps = 24
    
    with open("timings.json", "r") as f:
        scenes = json.load(f)
        
    total_chars = sum(s["char_count"] for s in scenes)
    
    edl_content = [
        "TITLE: AI_Generated_Video",
        "FCM: NON-DROP FRAME",
        ""
    ]
    
    current_timeline_frame = 0 # Timeline starts at 01:00:00:00 in Resolve usually, but EDL can specify 01:00:00:00
    timeline_start_offset = 1 * 3600 * fps # 01:00:00:00
    
    for idx, scene in enumerate(scenes, start=1):
        # Calculate duration in frames
        duration_frames = int((scene["char_count"] / total_chars) * audio_duration * fps)
        
        # Source timecode (always 0 to duration for still images)
        src_in = 0
        src_out = duration_frames
        
        # Record timecode
        rec_in = timeline_start_offset + current_timeline_frame
        rec_out = rec_in + duration_frames
        
        tc_src_in = format_tc(src_in)
        tc_src_out = format_tc(src_out)
        tc_rec_in = format_tc(rec_in)
        tc_rec_out = format_tc(rec_out)
        
        edl_content.append(f"{idx:03d}  AX       V     C        {tc_src_in} {tc_src_out} {tc_rec_in} {tc_rec_out}")
        # Note: image files often require the * FROM CLIP NAME: directive to link properly
        temp_idx = idx - 1
        c3 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c2 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c1 = chr(97 + (temp_idx % 26))
        filename = f"img_{c1}{c2}{c3}.jpg"
        edl_content.append(f"* FROM CLIP NAME: {filename}")
        edl_content.append("")
        
        current_timeline_frame += duration_frames
        
    with open("sequence.edl", "w") as f:
        f.write("\n".join(edl_content))
        
    print("Generated sequence.edl")

if __name__ == "__main__":
    main()
