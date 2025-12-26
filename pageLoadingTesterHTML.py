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

# --- SETUP BROWSER ---
options = Options()
options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    driver.get("https://app.joinhandshake.com/job-search")
    
    print("\n--- HTML INSPECTOR ---")
    print("1. Log in if needed.")
    print("2. Navigate to the job search page so a list of jobs is visible.")
    input("3. Press ENTER here to scan the page structure...")

    print("\n[ANALYZING STRUCTURE...]")

    # Strategy: Find all job links (which we know exist) and look at their parents
    # This reveals the structure of the "Card" without knowing the class name
    job_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/jobs/') and not(contains(@href, 'saved'))]")
    
    if len(job_links) == 0:
        print("❌ No job links found! Make sure you are on the search page with results visible.")
    else:
        print(f"✅ Found {len(job_links)} job links.")
        
        first_link = job_links[0]
        
        print("\n--- STRUCTURE OF FIRST JOB CARD ---")
        # We walk up the DOM tree 4 levels to show the container structure
        parent = first_link
        for i in range(1, 5):
            parent = parent.find_element(By.XPATH, "..")
            class_name = parent.get_attribute("class")
            tag_name = parent.tag_name
            print(f"Level {i} Up (<{tag_name}>): Class='{class_name}'")
            
            # If we hit a list item or a significant div, print its HTML
            if tag_name == "div" and "card" in class_name:
                print(f"   -> FOUND CARD CONTAINER at Level {i}!")
                print("-" * 40)
                print(parent.get_attribute('outerHTML')[:1000]) # Print first 1000 chars
                print("... (truncated)")
                print("-" * 40)
                break
            
            # Fallback: just print the 3rd level up if we don't find 'card'
            if i == 3:
                print("-" * 40)
                print(f"HTML of Level 3 Parent (<{tag_name}>):")
                print(parent.get_attribute('outerHTML')[:2000]) 
                print("-" * 40)

    print("\n--- NEXT BUTTON CHECK ---")
    try:
        # Check specific pagination buttons
        next_btn = driver.find_elements(By.XPATH, "//button[@aria-label='next page']")
        if next_btn:
            print(f"✅ Found Next Button: {next_btn[0].get_attribute('outerHTML')}")
        else:
            print("❌ Next button with aria-label='next page' NOT found.")
            
            # Print all buttons to see what pagination looks like
            all_btns = driver.find_elements(By.XPATH, "//button")
            print("Listing last 5 buttons on page (likely pagination):")
            for btn in all_btns[-5:]:
                print(f"Button: '{btn.text}' | HTML: {btn.get_attribute('outerHTML')[:100]}")

    except Exception as e:
        print(f"Error checking buttons: {e}")

except Exception as e:
    print(f"Critical Error: {e}")

finally:
    print("\nDone. Copy the output between the dashed lines.")