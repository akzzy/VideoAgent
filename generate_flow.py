import asyncio
import time
from playwright.async_api import async_playwright
import os

async def main():
    user_data_dir = r"C:\Users\akhil\AppData\Local\Microsoft\Edge\User Data"
    
    async with async_playwright() as p:
        print("Launching Edge with your profile...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 720}
        )
        
        page = await browser.new_page()
        os.makedirs("generated_images", exist_ok=True)
        
        with open("image_prompts.txt", "r", encoding="utf-8") as f:
            prompts = [line.strip() for line in f if line.strip()]
            
        print("Navigating to Google Flow...")
        await page.goto("https://labs.google/fx/tools/flow/project/14e9af57-4fc5-465a-8c9b-72f24440bbc3")
        
        # Wait a bit longer initially so the page and previous thumbnails fully load
        await page.wait_for_timeout(8000)
        
        prompt_selector = 'div[role="textbox"][data-slate-editor="true"]'
        
        # FIX 1: Extremely specific button selector. Looks for the button containing the "arrow_forward" icon!
        generate_button_selector = 'button:has(i.google-symbols:text-is("arrow_forward"))'
        
        for idx, prompt in enumerate(prompts, start=1):
            print(f"\nProcessing Scene {idx}...")
            print(f"Prompt: {prompt}")
            
            await page.click(prompt_selector)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(prompt, delay=10)
            
            await page.wait_for_timeout(1000)
            print("Clicking generate button...")
            
            # FIX 2: Ignore images that load instantly. True generation takes several seconds.
            click_time = time.time()
            
            def is_new_generated_image(response):
                if "flow-content.google/image/" in response.url and response.status == 200:
                    elapsed = time.time() - click_time
                    # If the image arrived in less than 4 seconds, it's an old thumbnail loading in the background
                    if elapsed > 4.0:
                        return True
                return False

            try:
                # We wait for the specific response from flow-content.google
                async with page.expect_response(is_new_generated_image, timeout=60000) as response_info:
                    click_time = time.time() # Reset exact time just before clicking
                    await page.click(generate_button_selector)
                
                image_response = await response_info.value
                image_bytes = await image_response.body()
                
                filename = f"generated_images/scene_{idx}.jpg"
                with open(filename, "wb") as f:
                    f.write(image_bytes)
                    
                print(f"✅ Successfully downloaded {filename}!")
            except Exception as e:
                print(f"❌ Failed to catch image for scene {idx}: {e}")
            
            # Give it a moment before typing the next prompt
            await page.wait_for_timeout(3000)
            
        print("\nAll images generated successfully!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
