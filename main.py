import os
import sys
import json
import time
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from google import genai
from google.genai import types
import whisper

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from pydantic import BaseModel, Field

# Constants
RESOLUTION_WIDTH = 1920
RESOLUTION_HEIGHT = 1080
FPS = 30
ASPECT_RATIO = "16:9"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not found in .env. API calls will fail.")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Data Models for Phase 1 ---
class Scene(BaseModel):
    scene_id: int
    exact_sentence_from_script: str
    image_prompt: str = Field(description="Action and environment description only, NOT the character's physical traits.")

class MasterScript(BaseModel):
    scenes: list[Scene]

# --- Phase 1: Creative Brain (Scene Breakdown) ---
def phase1_scene_breakdown(script_text: str) -> MasterScript:
    print("\n--- Phase 1: Generating scene breakdown from provided script ---")
    prompt = (
        f"Here is a narration script for a 2D cartoon video:\n\n{script_text}\n\n"
        f"Please break this script down into distinct visual scenes. Provide the exact text spoken "
        f"in each scene and a visual image generation prompt for that scene."
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MasterScript,
                    temperature=0.7,
                )
            )
            script_data = MasterScript.model_validate_json(response.text)
            
            # Save the JSON locally
            with open("master_script.json", "w") as f:
                f.write(script_data.model_dump_json(indent=2))
                
            print("Phase 1 Complete. master_script.json saved.")
            return script_data
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "503" in error_str or "UNAVAILABLE" in error_str:
                if attempt < max_retries - 1:
                    print(f"API busy or rate limited. Retrying in 20 seconds... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(20)
                    continue
            print(f"Phase 1 Error: {e}")
            return None

# --- Phase 2: Timing Extraction ---
def phase2_timing_extraction(script_data: MasterScript, audio_path: str):
    print("\n--- Phase 2: Timing Extraction via Whisper ---")
    if not script_data:
        print("No script data available. Skipping Phase 2.")
        return []
        
    if not os.path.exists(audio_path):
        print(f"Error: Could not find audio file at '{audio_path}'. Cannot proceed with timestamps.")
        return []

    print("Extracting timestamps via Whisper...")
    try:
        model = whisper.load_model("base") # base model for speed
        result = model.transcribe(audio_path, word_timestamps=True)
        
        # Map timestamps to scenes
        scene_timings = []
        words = []
        for segment in result['segments']:
            words.extend(segment.get('words', []))
            
        current_word_idx = 0
        for scene in script_data.scenes:
            scene_words = scene.exact_sentence_from_script.split()
            if current_word_idx < len(words):
                start_time = words[current_word_idx]['start']
                end_idx = min(current_word_idx + len(scene_words), len(words) - 1)
                end_time = words[end_idx]['end']
                duration = end_time - start_time
                
                scene_timings.append({
                    "scene_id": scene.scene_id,
                    "image_prompt": scene.image_prompt,
                    "start_time": start_time,
                    "duration": duration,
                    "start_frame": int(start_time * FPS),
                    "duration_frames": int(duration * FPS)
                })
                current_word_idx = end_idx + 1
            else:
                # Fallback timing if mapping fails towards the end
                scene_timings.append({
                    "scene_id": scene.scene_id,
                    "image_prompt": scene.image_prompt,
                    "start_time": 0,
                    "duration": 5.0,
                    "start_frame": 0,
                    "duration_frames": 5 * FPS
                })
        print("Phase 2 Complete. Audio timings extracted and mapped to scenes.")
        return scene_timings
    except Exception as e:
        print(f"Error during Whisper processing: {e}")
        return []

# --- Phase 3: Visual Generation ---
def phase3_visual_generation(scene_timings):
    print("\n--- Phase 3: Visual Generation ---")
    if not scene_timings:
        print("No scene timings available. Skipping Phase 3.")
        return
        
    from PIL import Image
    
    base_image_path = os.path.join("base_image", "base_image.png")
    base_img = None
    if os.path.exists(base_image_path):
        try:
            print("Loading base reference image locally using PIL...")
            base_img = Image.open(base_image_path)
        except Exception as e:
            print(f"Could not load base image: {e}")
    else:
        print(f"Warning: {base_image_path} not found. Ensure the reference image is placed there.")

    for scene in scene_timings:
        scene_id = scene['scene_id']
        prompt = f"Use the exact character provided in the reference image as the main subject. The image must be 16:9 widescreen. {scene['image_prompt']}"
        
        output_path = f"scene_{scene_id}.png"
        if os.path.exists(output_path):
            print(f"Skipping generation for {output_path}, already exists.")
            continue
            
        print(f"Generating image for scene {scene_id}...")
        try:
            # Prepare contents
            contents = [prompt]
            if base_img:
                contents.append(base_img)
                
            response = client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=contents,
            )
            
            if hasattr(response, 'parts') and response.parts:
                for part in response.parts:
                    if hasattr(part, 'text') and part.text is not None:
                        # Log any text returned (might be generation notes)
                        print(f"Model notes: {part.text}")
                    elif hasattr(part, 'inline_data') and part.inline_data is not None:
                        gen_img = part.as_image()
                        gen_img.save(output_path)
                        print(f"Successfully generated and saved {output_path}")
                        break
            
            time.sleep(2) # Rate limiting delay
            
        except Exception as e:
            print(f"Error generating image for scene {scene_id}: {e}")
            time.sleep(5) # Backoff on error
            
    print("Phase 3 Complete.")

# --- Phase 4: DaVinci Resolve Assembly via MCP ---
async def phase4_assembly(scene_timings, audio_path):
    print("\n--- Phase 4: DaVinci Resolve Assembly via MCP ---")
    if not scene_timings:
        print("No scene timings available. Skipping Phase 4.")
        return
        
    venv_python = os.path.join("davinci-resolve-mcp", "venv", "Scripts", "python.exe")
    server_script = os.path.join("davinci-resolve-mcp", "src", "server.py")
    
    python_exec = venv_python if os.path.exists(venv_python) else "python"
    print(f"Using Python executable for MCP: {python_exec}")
    
    server_params = StdioServerParameters(
        command=python_exec,
        args=[server_script],
        env=os.environ.copy()
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # 1. Create a timeline
                timeline_name = f"Auto_Timeline_{int(time.time())}"
                print(f"Creating Timeline: {timeline_name}")
                await session.call_tool("project", {"action": "create_timeline", "name": timeline_name})
                await asyncio.sleep(2)
                
                # 2. Add Audio
                abs_audio_path = os.path.abspath(audio_path)
                if os.path.exists(abs_audio_path):
                    print("Adding Audio...")
                    await session.call_tool("media_pool", {"action": "import_media", "paths": [abs_audio_path]})
                    await session.call_tool("timeline", {"action": "append_to_timeline", "paths": [abs_audio_path]})
                
                # 3. Add Images
                print("Assembling Scenes...")
                for scene in scene_timings:
                    img_path = os.path.abspath(f"scene_{scene['scene_id']}.png")
                    if os.path.exists(img_path):
                        await session.call_tool("media_pool", {"action": "import_media", "paths": [img_path]})
                        await session.call_tool("timeline", {"action": "append_to_timeline", "paths": [img_path]})
                        
                        # Apply dynamic zoom (Ken Burns)
                        await session.call_tool("timeline_item", {
                            "action": "set_transform",
                            "zoom_x": 1.1,
                            "zoom_y": 1.1
                        })
                        
                # 4. Render Setup
                print("Starting Render...")
                await session.call_tool("project", {
                    "action": "set_setting",
                    "setting_name": "timelineResolutionWidth",
                    "setting_value": str(RESOLUTION_WIDTH)
                })
                await session.call_tool("project", {
                    "action": "set_setting",
                    "setting_name": "timelineResolutionHeight",
                    "setting_value": str(RESOLUTION_HEIGHT)
                })
                await session.call_tool("project", {
                    "action": "set_setting",
                    "setting_name": "timelineFrameRate",
                    "setting_value": str(FPS)
                })
                
                await session.call_tool("project", {"action": "add_render_job"})
                await session.call_tool("project", {"action": "start_rendering"})
                
                print("Phase 4 Complete. Rendering initiated.")
    except Exception as e:
        print(f"Error communicating with MCP server: {e}")

async def main():
    print("=== Agentic Video Creation Pipeline (User Input Workflow) ===")
    
    script_path = "script.txt"
    audio_path = "audio.wav"
    
    if not os.path.exists(script_path):
        print(f"Error: '{script_path}' not found! Please create it and paste your script inside.")
        return
        
    if not os.path.exists(audio_path):
        print(f"Error: '{audio_path}' not found! Please place your voiceover file in the project folder.")
        return
        
    with open(script_path, "r", encoding="utf-8") as f:
        script_text = f.read().strip()
        
    if not script_text:
        print(f"Error: '{script_path}' is empty.")
        return

    script_data = phase1_scene_breakdown(script_text)
    scene_timings = phase2_timing_extraction(script_data, audio_path)
    phase3_visual_generation(scene_timings)
    await phase4_assembly(scene_timings, audio_path)
    
    print("\nPipeline Execution Finished.")

if __name__ == "__main__":
    asyncio.run(main())
