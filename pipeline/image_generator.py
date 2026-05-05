import asyncio
import os
import time
from playwright.async_api import async_playwright

FLOW_URL = "https://labs.google/fx/tools/flow/project/14e9af57-4fc5-465a-8c9b-72f24440bbc3"
EDGE_USER_DATA = r"C:\Users\akhil\AppData\Local\Microsoft\Edge\User Data"

PROMPT_SELECTOR = 'div[role="textbox"][data-slate-editor="true"]'
GENERATE_BTN_SELECTOR = 'button:has(i.google-symbols:text-is("arrow_forward"))'
ADD_BTN_SELECTOR = 'button:has(i.google-symbols:text-is("add_2"))'
BASE_IMAGE_SELECTOR = 'img[alt="base_image.png"]'


async def generate_images(scenes: list[dict], output_dir: str,
                          progress_callback=None, use_character: bool = False):
    """
    Uses Playwright to automate Google Flow image generation.
    If use_character is True, attaches base_image.png reference before generating.
    Saves images as img_a.jpg, img_b.jpg... in output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    total = len(scenes)

    async with async_playwright() as p:
        print("[Images] Launching Edge with your profile...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=EDGE_USER_DATA,
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 720}
        )

        page = await browser.new_page()

        # Navigate once at the start
        print("[Images] Navigating to Google Flow...")
        await page.goto(FLOW_URL)
        await page.wait_for_timeout(8000)

        for idx, scene in enumerate(scenes, start=1):
            temp_idx = idx - 1
            c3 = chr(97 + (temp_idx % 26))
            temp_idx //= 26
            c2 = chr(97 + (temp_idx % 26))
            temp_idx //= 26
            c1 = chr(97 + (temp_idx % 26))
            filename = f"img_{c1}{c2}{c3}.jpg"
            output_path = os.path.join(output_dir, filename)

            if os.path.exists(output_path):
                print(f"[Images] Skipping scene {idx} -- already exists.")
                if progress_callback:
                    progress_callback(idx, total, filename, skipped=True)
                continue

            prompt = scene["image_prompt"]
            print(f"[Images] Scene {idx}/{total}: {prompt[:60]}...")

            await page.click(PROMPT_SELECTOR)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prompt, delay=10)

            await page.wait_for_timeout(1000)

            # If character mode, attach the base_image reference
            if use_character:
                try:
                    print(f"[Images] Adding character reference...")
                    await page.click(ADD_BTN_SELECTOR)
                    await page.wait_for_timeout(2000)

                    # Click the base_image.png in the dialog
                    await page.wait_for_selector(BASE_IMAGE_SELECTOR, timeout=10000)
                    await page.click(BASE_IMAGE_SELECTOR)
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
                    await page.click(GENERATE_BTN_SELECTOR)

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

            await page.wait_for_timeout(3000)

        await browser.close()
        print("[Images] All done!")
