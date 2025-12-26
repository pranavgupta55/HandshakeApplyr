import time
import random
import csv
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
# Create a folder on your desktop called "handshake_bot" to store the database and chrome profile
BASE_DIR = os.path.expanduser("~/Desktop/handshake_bot") 
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

CSV_FILE = os.path.join(BASE_DIR, "application_log.csv")
CHROME_PROFILE = os.path.join(BASE_DIR, "chrome_profile")

# --- SETUP DATABASE ---
def log_job(company, title, status, notes=""):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Company', 'Title', 'Status', 'Notes', 'Date'])
        writer.writerow([company, title, status, notes, time.strftime("%Y-%m-%d %H:%M:%S")])
    print(f"[{status}] {company} - {title}: {notes}")

# --- SETUP BROWSER ---
options = Options()
# This allows you to log in once and save the session
options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --- THE AUTOMATION ---
try:
    # 1. Open Handshake
    driver.get("https://app.joinhandshake.com/job_search")
    
    print("--- INSTRUCTIONS ---")
    print("1. Please LOG IN manually in the browser window.")
    print("2. Set your filters (Internship, Remote, etc).")
    print("3. When the list of jobs is ready, press ENTER in this terminal to start.")
    input("Press Enter to start applying...")

    # Loop indefinitely (until no next page)
    while True:
        # Find all job cards in the left sidebar
        # Note: Class names change, so we look for the general container structure
        job_cards = driver.find_elements(By.XPATH, "//div[contains(@class, 'style__card___')]")
        
        for i in range(len(job_cards)):
            try:
                # Re-find elements to avoid "stale element" errors
                cards = driver.find_elements(By.XPATH, "//div[contains(@class, 'style__card___')]")
                if i >= len(cards): break
                card = cards[i]
                
                # Scroll into view and click
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                card.click()
                time.sleep(random.uniform(1.5, 3.0)) # Human-like pause

                # Scrape details
                company = driver.find_element(By.XPATH, "//a[contains(@class, 'style__employer-name___')]").text
                title = driver.find_element(By.XPATH, "//h1[contains(@class, 'style__job-title___')]").text

                # Check for "Apply" button
                apply_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Apply')]")
                
                if not apply_buttons:
                    log_job(company, title, "Skipped", "Already applied or external link")
                    continue

                apply_btn = apply_buttons[0]
                
                # Check if it's an "External Application" (opens new tab)
                if "external" in apply_btn.get_attribute("aria-label") or "External" in apply_btn.text:
                    log_job(company, title, "Saved for Later", "External Application")
                    continue

                # Click Apply
                apply_btn.click()
                time.sleep(2)

                # --- MODAL CHECK ---
                # Check the modal for "Cover Letter", "Transcript", or "Note"
                modal_text = driver.find_element(By.TAG_NAME, "body").text
                
                requires_extra = False
                missing_items = []

                if "Cover Letter" in modal_text and "Required" in modal_text: 
                    requires_extra = True
                    missing_items.append("Cover Letter")
                if "Transcript" in modal_text and "Required" in modal_text:
                    requires_extra = True
                    missing_items.append("Transcript")
                
                if requires_extra:
                    log_job(company, title, "Saved for Later", f"Requires: {', '.join(missing_items)}")
                    # Close modal (Escape key or click X)
                    webdriver.ActionChains(driver).send_keys("\ue00c").perform() # Press ESC
                else:
                    # SUBMIT!
                    # Look for the final submit button
                    submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit Application')]")
                    submit_btn.click()
                    
                    # Wait for success 
                    time.sleep(3)
                    log_job(company, title, "APPLIED", "Quick Apply Success")
                    
                    # Close success modal if it exists, or just move on
                    webdriver.ActionChains(driver).send_keys("\ue00c").perform()

            except Exception as e:
                print(f"Error on job {i}: {e}")
                continue
        
        # --- PAGINATION ---
        try:
            next_button = driver.find_element(By.XPATH, "//button[@aria-label='next page']")
            if next_button.is_enabled():
                next_button.click()
                print("Moving to next page...")
                time.sleep(5)
            else:
                print("End of pages reached.")
                break
        except:
            print("No next button found. Stopping.")
            break

except Exception as main_e:
    print(f"Critical Error: {main_e}")