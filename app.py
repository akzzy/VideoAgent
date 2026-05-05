import os
import json
import csv
import shutil
import threading
import asyncio
import queue
from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# SSE progress queues per project
_progress_queues: dict[str, queue.Queue] = {}


def project_path(name: str) -> str:
    return os.path.join(PROJECTS_DIR, name)


def project_status(name: str) -> dict:
    p = project_path(name)
    has_script = os.path.exists(os.path.join(p, "script.txt"))
    has_audio = any(os.path.exists(os.path.join(p, f"audio.{ext}")) for ext in ["wav", "mp3"])
    has_scenes = os.path.exists(os.path.join(p, "scenes.json"))
    images_dir = os.path.join(p, "generated_images")
    image_count = len([f for f in os.listdir(images_dir) if f.endswith(".jpg")]) if os.path.isdir(images_dir) else 0
    has_timeline = os.path.exists(os.path.join(p, "timeline_complete.xml"))

    step = 0
    if has_script: step = 1
    if has_audio: step = 2
    if has_scenes: step = 3
    if image_count > 0: step = 4
    if has_timeline: step = 5

    created = datetime.fromtimestamp(os.path.getctime(p)).strftime("%Y-%m-%d")
    return {
        "name": name,
        "created": created,
        "step": step,
        "has_script": has_script,
        "has_audio": has_audio,
        "has_scenes": has_scenes,
        "image_count": image_count,
        "has_timeline": has_timeline,
    }


# ── API Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/projects", methods=["GET"])
def list_projects():
    projects = []
    for name in sorted(os.listdir(PROJECTS_DIR)):
        if os.path.isdir(project_path(name)):
            projects.append(project_status(name))
    return jsonify(projects)


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.json
    name = data.get("name", "").strip().replace(" ", "_")
    if not name:
        return jsonify({"error": "Name is required"}), 400
    p = project_path(name)
    if os.path.exists(p):
        return jsonify({"error": "Project already exists"}), 409
    os.makedirs(p)
    return jsonify(project_status(name)), 201


@app.route("/api/projects/<name>", methods=["GET"])
def get_project(name):
    if not os.path.isdir(project_path(name)):
        return jsonify({"error": "Not found"}), 404
    return jsonify(project_status(name))


@app.route("/api/projects/<name>/script", methods=["POST"])
def save_script(name):
    p = project_path(name)
    if not os.path.isdir(p):
        return jsonify({"error": "Not found"}), 404
    data = request.json
    script = data.get("script", "").strip()
    if not script:
        return jsonify({"error": "Script is empty"}), 400
    with open(os.path.join(p, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script)
    return jsonify({"success": True})


@app.route("/api/projects/<name>/audio", methods=["POST"])
def upload_audio(name):
    p = project_path(name)
    if not os.path.isdir(p):
        return jsonify({"error": "Not found"}), 404
    if "audio" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["audio"]
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("wav", "mp3"):
        return jsonify({"error": "Only WAV or MP3 supported"}), 400
    # Remove old audio files
    for old_ext in ("wav", "mp3"):
        old = os.path.join(p, f"audio.{old_ext}")
        if os.path.exists(old):
            os.remove(old)
    save_path = os.path.join(p, f"audio.{ext}")
    file.save(save_path)
    return jsonify({"success": True, "filename": f"audio.{ext}"})


@app.route("/api/projects/<name>/settings", methods=["GET"])
def get_settings(name):
    settings_path = os.path.join(project_path(name), "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"use_character": False})


@app.route("/api/projects/<name>/settings", methods=["PUT"])
def save_settings(name):
    p = project_path(name)
    if not os.path.isdir(p):
        return jsonify({"error": "Not found"}), 404
    settings = request.json
    with open(os.path.join(p, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return jsonify({"success": True})


@app.route("/api/projects/<name>/generate-prompts", methods=["POST"])
def generate_prompts(name):
    p = project_path(name)
    script_path = os.path.join(p, "script.txt")
    if not os.path.exists(script_path):
        return jsonify({"error": "Script not found"}), 400

    with open(script_path, encoding="utf-8") as f:
        script_text = f.read()

    # Check settings
    use_character = False
    style = "cinematic"
    settings_path = os.path.join(p, "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
            use_character = settings.get("use_character", False)
            style = settings.get("style", "cinematic")

    try:
        from pipeline.scene_breakdown import generate_scenes
        scenes = generate_scenes(script_text, use_character=use_character, style=style)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Save scenes.json
    with open(os.path.join(p, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2)

    # Save CSV for review
    csv_path = os.path.join(p, "scenes_review.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Scene #", "Script Text", "Image Prompt"])
        for s in scenes:
            writer.writerow([s["scene_id"], s["script_text"], s["image_prompt"]])

    return jsonify({"success": True, "scenes": scenes})


@app.route("/api/projects/<name>/scenes", methods=["GET"])
def get_scenes(name):
    scenes_path = os.path.join(project_path(name), "scenes.json")
    if not os.path.exists(scenes_path):
        return jsonify({"error": "Scenes not generated yet"}), 404
    with open(scenes_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/projects/<name>/scenes", methods=["PUT"])
def update_scenes(name):
    p = project_path(name)
    scenes = request.json.get("scenes", [])
    if not scenes:
        return jsonify({"error": "No scenes provided"}), 400

    with open(os.path.join(p, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2)

    # Update CSV too
    csv_path = os.path.join(p, "scenes_review.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Scene #", "Script Text", "Image Prompt"])
        for s in scenes:
            writer.writerow([s["scene_id"], s["script_text"], s["image_prompt"]])

    # Save prompts txt
    prompts_path = os.path.join(p, "image_prompts.txt")
    with open(prompts_path, "w", encoding="utf-8") as f:
        for s in scenes:
            f.write(s["image_prompt"] + "\n")

    return jsonify({"success": True})


@app.route("/api/projects/<name>/generate-images", methods=["POST"])
def generate_images_route(name):
    p = project_path(name)
    scenes_path = os.path.join(p, "scenes.json")
    if not os.path.exists(scenes_path):
        return jsonify({"error": "Scenes not found"}), 400

    with open(scenes_path, encoding="utf-8") as f:
        scenes = json.load(f)

    output_dir = os.path.join(p, "generated_images")

    # Init SSE queue for this project
    _progress_queues[name] = queue.Queue()

    def progress_callback(idx, total, filename, skipped=False, error=None):
        q = _progress_queues.get(name)
        if q:
            q.put({"idx": idx, "total": total, "filename": filename,
                   "skipped": skipped, "error": error})

    # Check character setting
    use_character = False
    settings_path = os.path.join(p, "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            use_character = json.load(f).get("use_character", False)

    def run_async():
        try:
            from pipeline.image_generator import generate_images
            asyncio.run(generate_images(scenes, output_dir, progress_callback,
                                        use_character=use_character))
        except Exception as e:
            print(f"[Images] Thread error: {e}")
        finally:
            q = _progress_queues.get(name)
            if q:
                q.put({"done": True})

    t = threading.Thread(target=run_async, daemon=False)
    t.start()

    return jsonify({"success": True, "message": "Image generation started"})


@app.route("/api/projects/<name>/progress")
def progress_stream(name):
    def event_stream():
        q = _progress_queues.get(name, queue.Queue())
        while True:
            try:
                msg = q.get(timeout=120)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("done"):
                    break
            except queue.Empty:
                yield "data: {\"heartbeat\": true}\n\n"

    return Response(event_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/projects/<name>/images/<filename>")
def serve_image(name, filename):
    images_dir = os.path.join(project_path(name), "generated_images")
    return send_from_directory(images_dir, filename)


@app.route("/api/projects/<name>/build-video", methods=["POST"])
def build_video(name):
    p = project_path(name)
    scenes_path = os.path.join(p, "scenes.json")

    if not os.path.exists(scenes_path):
        return jsonify({"error": "Scenes not found"}), 400

    audio_path = None
    for ext in ("wav", "mp3"):
        candidate = os.path.join(p, f"audio.{ext}")
        if os.path.exists(candidate):
            audio_path = candidate
            break
    if not audio_path:
        return jsonify({"error": "Audio not found"}), 400

    with open(scenes_path, encoding="utf-8") as f:
        scenes = json.load(f)

    try:
        from pipeline.timing_extractor import extract_timings
        scenes_with_timings = extract_timings(scenes, audio_path)
    except Exception as e:
        return jsonify({"error": f"Timing extraction failed: {e}"}), 500

    # Save timings
    with open(os.path.join(p, "timings.json"), "w", encoding="utf-8") as f:
        json.dump(scenes_with_timings, f, indent=2)

    try:
        from pipeline.resolve_builder import build_timeline
        result = build_timeline(p, scenes_with_timings, audio_path, name)
    except Exception as e:
        return jsonify({"error": f"Resolve build failed: {e}"}), 500

    return jsonify(result)


@app.route("/api/projects/<name>/open-in-resolve", methods=["POST"])
def open_in_resolve(name):
    p = project_path(name)
    xml_path = os.path.join(p, "timeline_complete.xml")

    if not os.path.exists(xml_path):
        return jsonify({"error": "Timeline XML not found. Build the video first."}), 400

    abs_xml = os.path.abspath(xml_path)
    resolve_dir = os.environ.get("RESOLVE_INSTALL_PATH",
                                  r"C:\Program Files\Blackmagic Design\DaVinci Resolve")
    resolve_exe = os.path.join(resolve_dir, "Resolve.exe")
    helper_script = os.path.join(os.path.dirname(__file__), "resolve_import_helper.py")

    import subprocess as sp

    # 1. Launch Resolve if not running
    try:
        result = sp.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe"],
                        capture_output=True, text=True)
        if "Resolve.exe" not in result.stdout:
            if os.path.exists(resolve_exe):
                print("[Resolve] Launching DaVinci Resolve...")
                sp.Popen([resolve_exe], cwd=resolve_dir)
                import time
                time.sleep(60)  # Give Resolve time to fully start
    except Exception as e:
        print(f"[Resolve] Could not check/launch Resolve: {e}")

    # 2. Use Python 3.13 (compatible with fusionscript.dll) to import
    try:
        proc = sp.run(
            ["py", "-3.13", helper_script, name, abs_xml],
            capture_output=True, text=True, timeout=60
        )

        # Parse the JSON output from the helper script
        output = proc.stdout.strip()
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    return jsonify(data)
                except json.JSONDecodeError:
                    continue

        return jsonify({
            "success": False,
            "error": f"Import script failed. stdout: {proc.stdout[:300]}  stderr: {proc.stderr[:300]}",
            "xml_path": abs_xml
        }), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "xml_path": abs_xml
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5858, debug=False, threaded=True)
