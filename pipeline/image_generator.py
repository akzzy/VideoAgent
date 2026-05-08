import asyncio
import os
import time
import json
import random
import httpx
from playwright.async_api import async_playwright

FLOW_URL = "https://labs.google/fx/tools/flow/project/a876a7bb-9599-4e94-b4df-0a0e43fa483f"
EDGE_USER_DATA = r"C:\Users\akkzz\AppData\Local\Microsoft\Edge\User Data"

PROMPT_SELECTOR = 'div[role="textbox"][data-slate-editor="true"]'
GENERATE_BTN_SELECTOR = 'button:has(i.google-symbols:text-is("arrow_forward"))'
ADD_BTN_SELECTOR = 'button:has(i.google-symbols:text-is("add_2"))'
BASE_IMAGE_SELECTOR = 'img[alt="base_image.png"]'

BATCH_API_PATTERN = "flowMedia:batchGenerateImages"


def _scene_filename(idx: int) -> str:
    """Generate img_aaa.jpg style filename from 1-based index."""
    temp = idx - 1
    c3 = chr(97 + (temp % 26))
    temp //= 26
    c2 = chr(97 + (temp % 26))
    temp //= 26
    c1 = chr(97 + (temp % 26))
    return f"img_{c1}{c2}{c3}.jpg"


async def generate_images(scenes: list[dict], output_dir: str,
                          progress_callback=None, use_character: bool = False):
    """
    Uses Playwright to automate Google Flow image generation.
    Parallel architecture: Typist fires prompts every 5s, Catcher downloads in background.
    """
    os.makedirs(output_dir, exist_ok=True)
    total = len(scenes)

    # ── Build prompt → scene mapping & determine which scenes need generation ──
    prompt_to_scene: dict[str, dict] = {}
    pending_indices: set[int] = set()

    for idx, scene in enumerate(scenes, start=1):
        filename = _scene_filename(idx)
        output_path = os.path.join(output_dir, filename)

        if os.path.exists(output_path):
            print(f"[Images] Skipping scene {idx} -- already exists.")
            if progress_callback:
                progress_callback(idx, total, filename, skipped=True)
            continue

        prompt = scene["image_prompt"]
        prompt_to_scene[prompt] = {
            "idx": idx,
            "filename": filename,
            "output_path": output_path,
        }
        pending_indices.add(idx)

    if not pending_indices:
        print("[Images] All images already exist!")
        return

    print(f"[Images] {len(pending_indices)} images to generate, {total - len(pending_indices)} skipped.")

    # ── Shared state for Catcher ──
    downloaded: set[int] = set()
    download_errors: dict[int, str] = {}
    catcher_lock = asyncio.Lock()

    async def catcher_handler(response):
        """Background listener that catches completed image generation responses."""
        if BATCH_API_PATTERN not in response.url:
            return
        if response.status != 200:
            return

        try:
            data = await response.json()
        except Exception:
            return

        for media_item in data.get("media", []):
            image = media_item.get("image", {})
            gen_image = image.get("generatedImage", {})
            fife_url = gen_image.get("fifeUrl")
            prompt = gen_image.get("prompt", "")
            workflow_id = gen_image.get("workflowId", "")

            if not fife_url:
                continue

            # Match prompt to our scene mapping
            scene_info = prompt_to_scene.get(prompt)
            if not scene_info:
                print(f"[Catcher] Unknown prompt (not in our batch), skipping.")
                continue

            idx = scene_info["idx"]
            filename = scene_info["filename"]
            output_path = scene_info["output_path"]

            async with catcher_lock:
                if idx in downloaded:
                    continue
                downloaded.add(idx)

            # Download the image from fifeUrl
            try:
                print(f"[Catcher] Scene {idx} ready (workflow: {workflow_id[:12]}...) — downloading...")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    img_response = await client.get(fife_url)
                    img_response.raise_for_status()

                with open(output_path, "wb") as f:
                    f.write(img_response.content)

                print(f"[Catcher] ✓ Saved {filename} ({len(img_response.content)} bytes)")
                if progress_callback:
                    progress_callback(idx, total, filename)

            except Exception as e:
                print(f"[Catcher] ✗ Failed to download scene {idx}: {e}")
                async with catcher_lock:
                    downloaded.discard(idx)
                    download_errors[idx] = str(e)
                if progress_callback:
                    progress_callback(idx, total, filename, error=str(e))

    # ── Launch browser ──
    async with async_playwright() as p:
        print("[Images] Launching Edge with your profile...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=EDGE_USER_DATA,
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 720}
        )

        page = await browser.new_page()

        # Register the Catcher BEFORE navigating
        page.on("response", catcher_handler)

        print("[Images] Navigating to Google Flow...")
        await page.goto(FLOW_URL)
        await page.wait_for_timeout(8000)

        # ── The Typist: fire prompts with gaps ──
        scenes_to_type = [
            (idx, scene) for idx, scene in enumerate(scenes, start=1)
            if idx in pending_indices
        ]

        for i, (idx, scene) in enumerate(scenes_to_type):
            prompt = scene["image_prompt"]
            print(f"[Typist] Scene {idx}/{total}: {prompt[:60]}...")

            # Clear and type the prompt
            await page.click(PROMPT_SELECTOR)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prompt, delay=20)
            await page.wait_for_timeout(1000)

            # Attach character reference if needed
            if use_character:
                try:
                    print(f"[Typist] Adding character reference...")
                    await page.click(ADD_BTN_SELECTOR)
                    await page.wait_for_timeout(2000)
                    await page.wait_for_selector(BASE_IMAGE_SELECTOR, timeout=10000)
                    await page.click(BASE_IMAGE_SELECTOR)
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[Typist] Warning: Could not add character reference: {e}")

            # Click Generate
            await page.click(GENERATE_BTN_SELECTOR)
            print(f"[Typist] ✓ Fired scene {idx}")

            # Wait before typing next prompt (randomized to look natural)
            if i < len(scenes_to_type) - 1:
                base_wait = 20 if use_character else 15
                jitter = random.uniform(-3, 5)
                wait_time = int((base_wait + jitter) * 1000)
                print(f"[Typist] Waiting {wait_time/1000:.1f}s before next prompt...")
                await page.wait_for_timeout(wait_time)

        # ── Wait for all images to be downloaded by the Catcher ──
        print(f"\n[Images] All {len(scenes_to_type)} prompts fired. Waiting for downloads...")
        timeout_start = time.time()
        max_wait = 180  # 3 minutes max wait after last prompt

        while True:
            remaining = pending_indices - downloaded
            if not remaining:
                break
            if time.time() - timeout_start > max_wait:
                print(f"[Images] Timeout! {len(remaining)} images still pending: {remaining}")
                for idx in remaining:
                    fn = _scene_filename(idx)
                    if progress_callback:
                        progress_callback(idx, total, fn, error="Timed out waiting for generation")
                break
            await asyncio.sleep(1)

        # Clean up
        page.remove_listener("response", catcher_handler)
        await browser.close()

        success_count = len(downloaded)
        fail_count = len(pending_indices) - success_count
        print(f"\n[Images] Done! {success_count} downloaded, {fail_count} failed/timed out.")
