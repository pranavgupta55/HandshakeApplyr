import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
BASE_DIR = os.path.expanduser("~/Desktop/handshake_bot") 
CHROME_PROFILE = os.path.join(BASE_DIR, "chrome_profile")
DUMP_FILE = os.path.join(BASE_DIR, "full_page_dump.html")

# --- SETUP BROWSER ---
options = Options()
options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    driver.get("https://app.joinhandshake.com/job-search")
    
    print("\n--- FULL HTML DUMP ---")
    print("1. Log in if needed.")
    print("2. Navigate to the job search page.")
    print("3. Scroll down a little to ensure job cards are loaded.")
    input("4. Press ENTER here to dump the HTML...")

    # Get the full HTML
    full_html = driver.page_source

    # Print to terminal
    print("\n" + "="*50)
    print("BEGIN HTML OUTPUT")
    print("="*50 + "\n")
    
    print(full_html)
    
    print("\n" + "="*50)
    print("END HTML OUTPUT")
    print("="*50 + "\n")

    # Also save to file for safety
    with open(DUMP_FILE, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    print(f"✅ The HTML has also been saved to: {DUMP_FILE}")

except Exception as e:
    print(f"Error: {e}")

finally:
    # driver.quit() # Keep browser open
    pass