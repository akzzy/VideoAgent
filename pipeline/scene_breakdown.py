import os
import json
from google import genai

STYLE_PRESETS = {
    "cinematic": "dark, dramatic, cinematic, photorealistic",
    "2d_cartoon": "2D cartoon style, flat colors, bold outlines, animated look",
    "anime": "anime style, vibrant colors, detailed cel-shading, Japanese animation aesthetic",
    "realistic": "ultra-realistic, photographic, high detail, natural lighting",
    "watercolor": "soft watercolor painting style, flowing colors, artistic, painterly",
    "3d_render": "3D rendered, Pixar-style, smooth shading, volumetric lighting",
    "comic_book": "comic book style, halftone dots, bold ink lines, dynamic panels",
    "oil_painting": "classical oil painting style, rich textures, dramatic chiaroscuro lighting",
}


def generate_scenes(script_text: str, use_character: bool = False, style: str = "cinematic", target_duration: int = 5, creative_direction: str = "") -> list[dict]:
    """
    Uses Gemini 3.1 Flash lite to break a script into scenes with image prompts.
    Splits long sentences so no scene exceeds ~7 seconds of narration.
    If use_character is True, prompts will reference a consistent character.
    style: key from STYLE_PRESETS for consistent visual style.
    Returns a list of dicts: [{scene_id, script_text, image_prompt}]
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    style_desc = STYLE_PRESETS.get(style, STYLE_PRESETS["cinematic"])

    character_instruction = ""
    if use_character:
        character_instruction = f"""
    IMPORTANT: This video features a CONSISTENT CHARACTER throughout. A reference image will be provided during generation.
    
    CHARACTER CONSISTENCY & POSING:
    - Study the reference image carefully. Keep the character's appearance (face, hair, clothing, proportions) the SAME in every image.
    - Always refer to them as "the character". Do NOT invent names or change their look.
    - CRITICAL: The reference image shows the character in a neutral standing pose. Do NOT copy this pose! You MUST explicitly describe the character in a NEW, DYNAMIC pose performing an action relevant to the scene (e.g., "sitting at a desk typing", "running", "pointing excitedly", "looking confused").

    ART STYLE & COMPOSITION:
    - The visual style is: {style_desc}
    - ALL elements in the image (character, background, objects, props) must match this SAME style.
    - CRITICAL: Avoid plain white or solid-color empty backgrounds. ALWAYS describe a fully realized environment or detailed background elements (e.g., "a busy office with large windows", "a textured wall with abstract shapes", "a bustling city street").
    """
    else:
        character_instruction = f"""
    ART STYLE & COMPOSITION:
    - The visual style is: {style_desc}
    - CRITICAL: Avoid plain white or solid-color empty backgrounds. ALWAYS describe a fully realized environment or detailed background elements.
    """

    word_count = len(script_text.split())
    estimated_audio_length = word_count / 2.75  # ~2.75 words per second
    target_scenes = max(1, round(estimated_audio_length / target_duration))

    creative_dir_block = ""
    if creative_direction:
        creative_dir_block = f"""
    CREATIVE DIRECTION FROM THE USER:
    {creative_direction}
    Use this information to make image prompts accurate. Apply this context to EVERY image prompt.
    """

    system_prompt = f"""You are a video production assistant. 
    Break the given script into individual scenes for a video.
    
    ABSOLUTE RULE — PRESERVE EVERY WORD:
    - You MUST use EVERY SINGLE WORD from the original script. No word may be skipped, removed, summarized, or paraphrased.
    - When you concatenate all scene "script_text" fields in order, the result MUST be the EXACT original script, word for word.
    - If you drop even one word, the audio and images will go out of sync and the video will be ruined.
    
    CRITICAL RULE FOR SCENE LENGTH (PACING):
    - The script has {word_count} words and will take approximately {int(estimated_audio_length)} seconds to read.
    - The user requested an image every {target_duration} seconds.
    - Therefore, YOU MUST BREAK THIS SCRIPT INTO APPROXIMATELY {target_scenes} SCENES.
    - To reach {target_scenes} scenes, you MUST break single sentences into multiple shorter fragments. 
    - Example: "When they spotted you," (Scene 1) "they could jump 8 feet high" (Scene 2) "just taking off from the ground." (Scene 3).
    - Do NOT be afraid to make scenes 3-5 words long. Split aggressively to hit the target, but NEVER drop any words.
    
    TEXT IN IMAGES:
    - CRITICAL: Do NOT request long sentences, paragraphs, or banners of text in the generated images.
    - Rely on visual storytelling rather than written text. If you must include text, keep it to 1-2 very small words max (e.g., a sign that says "BANK").

    {character_instruction}
    {creative_dir_block}
    
    For each scene, create a detailed, vivid image prompt suitable for an AI image generator.
    The image prompt should describe a stunning visual that matches the script text.
    Make the prompts specific, descriptive, and visually rich.
    
    STYLE: Every image prompt MUST end with this style tag: "{style_desc}"
    This ensures all images share a consistent visual style.

    Respond ONLY with valid JSON in this exact format:
    {{
      "scenes": [
        {{
          "scene_id": 1,
          "script_text": "exact text from the script for this scene",
          "image_prompt": "detailed image generation prompt, {style_desc}"
        }}
      ]
    }}
    """

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=f"{system_prompt}\n\nScript:\n{script_text}"
    )

    raw = response.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    return data["scenes"]
