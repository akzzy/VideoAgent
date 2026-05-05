import os
import subprocess
import json


def build_timeline(project_dir: str, scenes_with_timings: list[dict], audio_path: str, project_name: str) -> dict:
    """
    Generates FCPXML timeline file with images, audio, and slow zoom animation.
    Returns dict with success status and xml_path.
    """
    fps = 30

    # Get actual audio duration for accurate frame count
    try:
        dur_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True
        )
        audio_duration_secs = float(dur_result.stdout.strip())
    except Exception:
        audio_duration_secs = 0
    audio_total_frames = round(audio_duration_secs * fps) if audio_duration_secs > 0 else None

    # Get audio sample info via ffprobe
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate,channels",
             "-of", "json", audio_path],
            capture_output=True, text=True
        )
        audio_info = json.loads(probe.stdout)
        stream = audio_info.get("streams", [{}])[0]
        sample_rate = int(stream.get("sample_rate", 44100))
        channels = int(stream.get("channels", 2))
    except Exception:
        sample_rate = 44100
        channels = 1

    total_frames = sum(s["duration_frames"] for s in scenes_with_timings)
    if total_frames == 0:
        return {"success": False, "error": "No frames to render"}

    # Use actual audio duration for the sequence/audio clip (prevents drift)
    seq_frames = audio_total_frames if audio_total_frames else total_frames

    abs_audio = os.path.abspath(audio_path).replace("\\", "/")
    audio_url = f"file://localhost/{abs_audio}"

    timeline_name = project_name.replace(" ", "_")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="4">',
        f'  <sequence id="seq-{timeline_name}">',
        f'    <name>{timeline_name}</name>',
        f'    <duration>{seq_frames}</duration>',
        f'    <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '    <media>',
        '      <video>',
        '        <format><samplecharacteristics>',
        '          <width>1920</width><height>1080</height>',
        '        </samplecharacteristics></format>',
        '        <track>',
    ]

    current_frame = 0
    for idx, scene in enumerate(scenes_with_timings, start=1):
        temp_idx = idx - 1
        c3 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c2 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c1 = chr(97 + (temp_idx % 26))
        filename = f"img_{c1}{c2}{c3}.jpg"
        filepath = os.path.join(project_dir, "generated_images", filename)
        fileurl = f"file://localhost/{os.path.abspath(filepath).replace(chr(92), '/')}"
        dur = scene["duration_frames"]

        xml_lines += [
            f'          <clipitem id="v-{idx}">',
            f'            <name>{filename}</name>',
            f'            <duration>{dur}</duration>',
            f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            f'            <start>{current_frame}</start>',
            f'            <end>{current_frame + dur}</end>',
            '            <in>0</in>',
            f'            <out>{dur}</out>',
            f'            <file id="f-{idx}">',
            f'              <name>{filename}</name>',
            f'              <pathurl>{fileurl}</pathurl>',
            f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
            '              <duration>864000</duration>',
            '              <media><video><samplecharacteristics>',
            '                <width>1920</width><height>1080</height>',
            '              </samplecharacteristics></video></media>',
            '            </file>',
        ]

        # Ken Burns zoom — scale based on clip duration in seconds
        dur_secs = scene.get("duration", dur / fps)
        if dur_secs <= 2:
            end_scale = 105
        elif dur_secs <= 5:
            end_scale = 110
        else:
            end_scale = 115
        print(f"  Scene {idx}: {dur_secs:.1f}s -> zoom {end_scale}%")

        xml_lines += [
            '            <filter>',
            '              <effect>',
            '                <name>Basic Motion</name>',
            '                <effectid>basic</effectid>',
            '                <effectcategory>motion</effectcategory>',
            '                <effecttype>motion</effecttype>',
            '                <mediatype>video</mediatype>',
            '                <parameter>',
            '                  <parameterid>scale</parameterid>',
            '                  <name>Scale</name>',
            '                  <valuemin>0</valuemin>',
            '                  <valuemax>1000</valuemax>',
            '                  <keyframe>',
            '                    <when>0</when>',
            '                    <value>100</value>',
            '                  </keyframe>',
            '                  <keyframe>',
            f'                    <when>{dur}</when>',
            f'                    <value>{end_scale}</value>',
            '                  </keyframe>',
            '                </parameter>',
            '              </effect>',
            '            </filter>',
            '          </clipitem>',
        ]
        current_frame += dur

    xml_lines += [
        '        </track>',
        '      </video>',
        '      <audio>',
        '        <track>',
        '          <clipitem id="a-1">',
        '            <name>audio</name>',
        f'            <duration>{seq_frames}</duration>',
        f'            <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        '            <start>0</start>',
        f'            <end>{seq_frames}</end>',
        '            <in>0</in>',
        f'            <out>{seq_frames}</out>',
        '            <file id="f-audio">',
        '              <name>audio</name>',
        f'              <pathurl>{audio_url}</pathurl>',
        f'              <rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>',
        f'              <duration>{seq_frames}</duration>',
        '              <media><audio>',
        '                <samplecharacteristics>',
        '                  <depth>16</depth>',
        f'                  <samplerate>{sample_rate}</samplerate>',
        '                </samplecharacteristics>',
        f'                <channelcount>{channels}</channelcount>',
        '              </audio></media>',
        '            </file>',
        '            <sourcetrack>',
        '              <mediatype>audio</mediatype>',
        '              <trackindex>1</trackindex>',
        '            </sourcetrack>',
        '          </clipitem>',
        '        </track>',
        '      </audio>',
        '    </media>',
        '  </sequence>',
        '</xmeml>',
    ]

    xml_path = os.path.join(project_dir, "timeline_complete.xml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines))

    print(f"[Resolve] Generated {xml_path}")
    return {"success": True, "xml_path": os.path.abspath(xml_path), "timeline": timeline_name}
