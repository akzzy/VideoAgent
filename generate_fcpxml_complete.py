import json
import os

def main():
    audio_duration = 38.62
    fps = 24
    sample_rate = 32000
    channels = 1

    with open("timings.json", "r") as f:
        scenes = json.load(f)

    total_chars = sum(s["char_count"] for s in scenes)
    total_frames = int(audio_duration * fps)
    total_audio_samples = int(audio_duration * sample_rate)

    abs_audio = os.path.abspath("audio.wav").replace("\\", "/")
    audio_url = f"file://localhost/{abs_audio}"

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="4">',
        '  <sequence id="Sequence_Final">',
        '    <name>AI_Video_Complete</name>',
        f'    <duration>{total_frames}</duration>',
        '    <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>',
        '    <media>',
        '      <video>',
        '        <format>',
        '          <samplecharacteristics>',
        '            <width>1920</width>',
        '            <height>1080</height>',
        '          </samplecharacteristics>',
        '        </format>',
        '        <track>',
    ]

    current_start = 0
    for idx, scene in enumerate(scenes, start=1):
        temp_idx = idx - 1
        c3 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c2 = chr(97 + (temp_idx % 26))
        temp_idx //= 26
        c1 = chr(97 + (temp_idx % 26))
        filename = f"img_{c1}{c2}{c3}.jpg"
        filepath = os.path.abspath(f"generated_images/{filename}").replace("\\", "/")
        fileurl = f"file://localhost/{filepath}"

        duration_frames = int((scene["char_count"] / total_chars) * total_frames)
        if idx == len(scenes):
            duration_frames = total_frames - current_start

        xml.extend([
            f'          <clipitem id="v-{idx}">',
            f'            <name>{filename}</name>',
            f'            <duration>{duration_frames}</duration>',
            '            <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>',
            f'            <start>{current_start}</start>',
            f'            <end>{current_start + duration_frames}</end>',
            '            <in>0</in>',
            f'            <out>{duration_frames}</out>',
            f'            <file id="f-{idx}">',
            f'              <name>{filename}</name>',
            f'              <pathurl>{fileurl}</pathurl>',
            '              <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>',
            '              <duration>864000</duration>',
            '              <media><video><samplecharacteristics>',
            '                <width>1920</width><height>1080</height>',
            '              </samplecharacteristics></video></media>',
            '            </file>',
            '          </clipitem>',
        ])
        current_start += duration_frames

    xml.extend([
        '        </track>',
        '      </video>',
        '      <audio>',
        '        <track>',
        f'          <clipitem id="a-1">',
        f'            <name>audio.wav</name>',
        f'            <duration>{total_frames}</duration>',
        '            <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>',
        '            <start>0</start>',
        f'            <end>{total_frames}</end>',
        '            <in>0</in>',
        f'            <out>{total_frames}</out>',
        '            <trackindex>1</trackindex>',
        f'            <file id="f-audio">',
        '              <name>audio.wav</name>',
        f'              <pathurl>{audio_url}</pathurl>',
        '              <rate><timebase>24</timebase><ntsc>FALSE</ntsc></rate>',
        f'              <duration>{total_frames}</duration>',
        '              <media>',
        '                <audio>',
        f'                  <samplecharacteristics>',
        f'                    <depth>16</depth>',
        f'                    <samplerate>{sample_rate}</samplerate>',
        '                  </samplecharacteristics>',
        f'                  <channelcount>{channels}</channelcount>',
        '                </audio>',
        '              </media>',
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
    ])

    with open("timeline_complete.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    print("Generated timeline_complete.xml")

if __name__ == "__main__":
    main()
