import sys
import json
import os

def get_resolve():
    try:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")
    except ImportError:
        pass
    
    # Try finding the module in the default installation paths
    ext = ".so"
    if sys.platform.startswith("darwin"):
        path = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules/"
    elif sys.platform.startswith("win") or sys.platform.startswith("cygwin"):
        path = os.getenv('PROGRAMDATA') + "\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules\\"
        ext = ".dll"
    elif sys.platform.startswith("linux"):
        path = "/opt/resolve/libs/Fusion/Modules/"

    if path not in sys.path:
        sys.path.append(path)
        
    try:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")
    except Exception as e:
        print("Could not load DaVinciResolveScript:", e)
        return None

def main():
    resolve = get_resolve()
    if not resolve:
        print("Resolve not found.")
        return
        
    projectManager = resolve.GetProjectManager()
    project = projectManager.GetCurrentProject()
    mediaPool = project.GetMediaPool()
    
    # Load timings
    with open("timings.json", "r") as f:
        scenes = json.load(f)
        
    total_chars = sum(s["char_count"] for s in scenes)
    audio_duration = 38.62
    fps = float(project.GetSetting("timelineFrameRate"))
    if fps == 0: fps = 24.0
    
    # First, find the items in the media pool
    root_folder = mediaPool.GetRootFolder()
    clips = root_folder.GetClipList()
    
    # Map clips by name
    clip_map = {clip.GetName(): clip for clip in clips}
    
    print("Found clips in Media Pool:", list(clip_map.keys()))
    
    # Create a new timeline
    timeline_name = "Perfect_Timeline"
    timeline = mediaPool.CreateEmptyTimeline(timeline_name)
    if not timeline:
        print("Failed to create timeline.")
        return
        
    project.SetCurrentTimeline(timeline)
    
    # Add video clips with specific durations
    timeline_items = []
    
    for idx, scene in enumerate(scenes, start=1):
        temp_idx = idx - 1
        c3 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c2 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c1 = chr(97 + (temp_idx % 26))
        clip_name = f"img_{c1}{c2}{c3}.jpg"
        
        if clip_name not in clip_map:
            print(f"Clip {clip_name} not found in Media Pool!")
            continue
            
        clip = clip_map[clip_name]
        duration_frames = int((scene["char_count"] / total_chars) * audio_duration * fps)
        
        # In DaVinci Resolve 18.1+, AppendToTimeline supports subclip dicts
        item_info = {
            "mediaPoolItem": clip,
            "startFrame": 0,
            "endFrame": duration_frames - 1 # inclusive
        }
        timeline_items.append(item_info)
        
    # Append all video items at once
    print(f"Appending {len(timeline_items)} video items to timeline...")
    success = mediaPool.AppendToTimeline(timeline_items)
    print("Video append success:", success)
    
    # Now, append audio. We want it to start at 0.
    # To put it on track 1 at time 0, since there are no audio clips, 
    # actually, AppendToTimeline adds to the end of the timeline overall.
    # To add to a specific track at a specific time, we need to use a different method.
    # But wait! If we append the audio FIRST (when the timeline is empty), it starts at 0.
    # Then we append the video clips! Let's try creating another timeline and doing that.
    
    timeline2 = mediaPool.CreateEmptyTimeline("Perfect_Timeline_Synced")
    project.SetCurrentTimeline(timeline2)
    
    if "audio.wav" in clip_map:
        print("Appending audio first...")
        mediaPool.AppendToTimeline([{"mediaPoolItem": clip_map["audio.wav"]}])
    else:
        print("audio.wav not found in Media Pool!")
        
    print("Now appending video items...")
    success = mediaPool.AppendToTimeline(timeline_items)
    print("Video append success:", success)
    
    print("Done! Check 'Perfect_Timeline_Synced' in Resolve.")

if __name__ == "__main__":
    main()
