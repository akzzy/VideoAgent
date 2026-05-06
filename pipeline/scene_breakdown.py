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


def generate_scenes(script_text: str, use_character: bool = False, style: str = "cinematic") -> list[dict]:
    """
    Uses Gemini 2.5 Flash to break a script into scenes with image prompts.
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

    system_prompt = f"""You are a video production assistant. 
    Break the given script into individual scenes for a video.
    
    CRITICAL RULE FOR SCENE LENGTH:
    - Each scene should be 1-2 sentences, roughly 12-18 words of narration.
    - At ~3 words/second, each scene should last approximately 4-6 seconds when spoken.
    - Do NOT create scenes longer than ~20 words. Split them if needed.
    - Do NOT create scenes shorter than ~8 words unless it's a very short impactful line.
    
    TEXT IN IMAGES:
    - CRITICAL: Do NOT request long sentences, paragraphs, or banners of text in the generated images.
    - Rely on visual storytelling rather than written text. If you must include text, keep it to 1-2 very small words max (e.g., a sign that says "BANK").

    {character_instruction}
    
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
        model="gemini-2.5-flash",
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
