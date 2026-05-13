import asyncio
import os
import time
import json
import random
import httpx
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

FLOW_URL = "https://labs.google/fx/tools/flow/project/4b0a194c-3b99-4c92-af01-e342f8b57455"
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


async def _human_click(page, selector):
    """Move mouse to element with slight randomness, then click — avoids teleporting."""
    element = await page.wait_for_selector(selector, timeout=10000)
    box = await element.bounding_box()
    if box:
        # Click at a slightly random offset within the element
        x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await page.wait_for_timeout(random.randint(50, 150))
        await page.mouse.click(x, y)
    else:
        await page.click(selector)


async def generate_images(scenes: list[dict], output_dir: str,
                          progress_callback=None, use_character: bool = False,
                          parallel: bool = False):
    """
    Uses Playwright to automate Google Flow image generation.
    parallel=False (default): Sequential mode — generates one image at a time, waits for each.
    parallel=True: Parallel Typist/Catcher mode — fires prompts with gaps, downloads in background.
    """
    if parallel:
        await _generate_parallel(scenes, output_dir, progress_callback, use_character)
    else:
        await _generate_sequential(scenes, output_dir, progress_callback, use_character)


# ═══════════════════════════════════════════════════════════════════
#  SEQUENTIAL MODE (Original — one at a time, safe)
# ═══════════════════════════════════════════════════════════════════

async def _generate_sequential(scenes: list[dict], output_dir: str,
                                progress_callback=None, use_character: bool = False):
    """Generate images one at a time, waiting for each to complete before moving on."""
    os.makedirs(output_dir, exist_ok=True)
    total = len(scenes)

    async with Stealth().use_async(async_playwright()) as p:
        print("[Images] Launching Edge with your profile (stealth mode)...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=EDGE_USER_DATA,
            channel="msedge",
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )

        page = await browser.new_page()

        # Navigate once at the start
        print("[Images] Navigating to Google Flow...")
        await page.goto(FLOW_URL)
        await page.wait_for_timeout(8000)

        for idx, scene in enumerate(scenes, start=1):
            filename = _scene_filename(idx)
            output_path = os.path.join(output_dir, filename)

            if os.path.exists(output_path):
                print(f"[Images] Skipping scene {idx} -- already exists.")
                if progress_callback:
                    progress_callback(idx, total, filename, skipped=True)
                continue

            prompt = scene["image_prompt"]
            print(f"[Images] Scene {idx}/{total}: {prompt[:60]}...")

            await _human_click(page, PROMPT_SELECTOR)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            # Randomized typing speed to look human
            await page.keyboard.type(prompt, delay=random.randint(15, 35))

            await page.wait_for_timeout(random.randint(800, 1500))

            # If character mode, attach the base_image reference
            if use_character:
                try:
                    print(f"[Images] Adding character reference...")
                    await _human_click(page, ADD_BTN_SELECTOR)
                    await page.wait_for_timeout(2000)

                    # Click the base_image.png in the dialog
                    await page.wait_for_selector(BASE_IMAGE_SELECTOR, timeout=10000)
                    await _human_click(page, BASE_IMAGE_SELECTOR)
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[Images] Warning: Could not add character reference: {e}")

            click_time = time.time()

            def is_new_generated_image(response):
                if "flow-content.google/image/" in response.url and response.status == 200:
                    elapsed = time.time() - click_time
                    if elapsed > 4.0:
                        return True
                return False

            try:
                async with page.expect_response(is_new_generated_image, timeout=90000) as response_info:
                    click_time = time.time()
                    await _human_click(page, GENERATE_BTN_SELECTOR)

                image_response = await response_info.value
                image_bytes = await image_response.body()

                with open(output_path, "wb") as f:
                    f.write(image_bytes)

                print(f"[Images] OK - Saved {filename}")
                if progress_callback:
                    progress_callback(idx, total, filename)

            except Exception as e:
                print(f"[Images] FAIL - Scene {idx}: {e}")
                if progress_callback:
                    progress_callback(idx, total, filename, error=str(e))

            # Brief cooldown before typing next prompt (2-4 seconds, randomized)
            wait = random.randint(2000, 4000)
            print(f"[Images] Cooldown {wait/1000:.1f}s...")
            await page.wait_for_timeout(wait)

        await browser.close()
        print("[Images] All done!")


# ═══════════════════════════════════════════════════════════════════
#  PARALLEL MODE (Typist/Catcher — faster but riskier)
# ═══════════════════════════════════════════════════════════════════

async def _generate_parallel(scenes: list[dict], output_dir: str,
                              progress_callback=None, use_character: bool = False):
    """Parallel mode: Typist fires prompts with gaps, Catcher downloads in background."""
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
