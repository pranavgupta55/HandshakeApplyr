import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- CONFIGURATION ---
BASE_DIR = os.path.expanduser("~/Desktop/handshake_bot") 
CHROME_PROFILE = os.path.join(BASE_DIR, "chrome_profile")
DEBUG_FILE = os.path.join(BASE_DIR, "handshake_source.html")

# --- SETUP BROWSER ---
options = Options()
options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    driver.get("https://app.joinhandshake.com/job-search")
    
    print("\n--- DEBUG MODE ---")
    print("1. Log in and navigate to your job search page.")
    print("2. Make sure job listings are visible on the screen.")
    input("3. Press ENTER here when ready to scrape...")

    # Save full HTML to file
    with open(DEBUG_FILE, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"\n[SUCCESS] Full HTML saved to: {DEBUG_FILE}")

    # --- DIAGNOSTICS ---
    print("\n--- DIAGNOSTICS ---")
    print(f"Current URL: {driver.current_url}")
    
    # Check for Pagination Buttons
    print("\n--- CHECKING PAGINATION ---")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    nav_buttons = [b.text for b in buttons if b.text.strip() != ""]
    print(f"Visible Buttons (First 20): {nav_buttons[:20]}")
    
    # Check for specific 'Next' button attributes often used by Handshake
    next_btns = driver.find_elements(By.XPATH, "//button[@aria-label='next page']")
    print(f"Buttons with aria-label='next page': {len(next_btns)}")

    # Check for Job Cards (looking for common structures)
    print("\n--- POTENTIAL JOB CARDS ---")
    # Strategy 1: Look for any div with 'card' in the class name
    card_divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'card')]")
    print(f"Divs with 'card' in class: {len(card_divs)}")
    
    if len(card_divs) > 0:
        print(f"Sample Class Name from first result: {card_divs[0].get_attribute('class')}")

    # Strategy 2: Look for 'href' links that point to jobs
    job_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/jobs/')]")
    print(f"Links containing '/jobs/': {len(job_links)}")
    if len(job_links) > 0:
        print(f"Sample Job Link Parent Class: {job_links[0].find_element(By.XPATH, '..').get_attribute('class')}")

    print("\n-------------------")
    print("Please copy the output above and paste it into the chat.")

except Exception as e:
    print(f"Error: {e}")

finally:
    # driver.quit() # Keep browser open so you can inspect if needed
    pass