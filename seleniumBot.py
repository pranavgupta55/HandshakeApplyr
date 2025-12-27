import time
import random
import csv
import os
import re
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException
)
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "handshake_data")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DEFAULT_CSV_NAME = "application_log.csv"
CHROME_PROFILE = os.path.join(DATA_DIR, "chrome_profile")

# Strict columns for CSV
FIELDNAMES = [
    'Job ID', 'Date', 'Status', 'Requirements', 'Company', 'Title', 
    'Job Link', 'Location', 'Pay', 'Job Type'
]

# --- CSV & HISTORY ---

def get_csv_filepath():
    """Ensures we don't overwrite files with different headers."""
    default_path = os.path.join(DATA_DIR, DEFAULT_CSV_NAME)
    if not os.path.exists(default_path): return default_path
    
    try:
        with open(default_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
                if headers == FIELDNAMES: return default_path
            except StopIteration: return default_path # Empty file is fine
    except: pass
    
    # If headers mismatch, create new file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"[INFO] Schema change detected. Creating new CSV.")
    return os.path.join(DATA_DIR, f"application_log_{timestamp}.csv")

def init_csv(filepath):
    if not os.path.exists(filepath):
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
    return filepath

def load_history(filepath):
    processed = set()
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('Job ID'):
                        processed.add(row['Job ID'])
        except Exception: pass
    print(f"[INIT] Loaded history: {len(processed)} jobs.")
    return processed

def log_to_csv(filepath, data):
    try:
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            # Sanitize None -> ""
            clean = {k: (v if v is not None else "") for k, v in data.items()}
            writer.writerow(clean)
    except Exception as e:
        print(f"[ERROR] CSV Write: {e}")

# --- ROBUST DATA EXTRACTION ---

def get_card_data(card_element):
    """
    Extracts high-quality data from the List Card (Left Sidebar).
    This serves as the PRIMARY source of truth.
    """
    data = {
        'Job ID': 'unknown',
        'Company': 'Unknown',
        'Title': 'Unknown', 
        'Job Link': '',
        'Location': ''
    }
    
    try:
        # 1. Job ID from data-hook (Most Robust)
        # Format: data-hook="job-result-card | 10540568"
        hook = card_element.get_attribute("data-hook")
        if hook and "|" in hook:
            data['Job ID'] = hook.split("|")[1].strip()
            data['Job Link'] = f"https://app.joinhandshake.com/jobs/{data['Job ID']}"

        # 2. Company Name from Image Alt or Text
        # <img ... alt="NeuralSeek" ...>
        try:
            img = card_element.find_element(By.TAG_NAME, "img")
            data['Company'] = img.get_attribute("alt")
        except:
            # Fallback to text parsing (Company is usually 2nd line)
            lines = card_element.text.split('\n')
            if len(lines) > 1: data['Company'] = lines[1]

        # 3. Job Title
        # Often in an aria-label or strong text
        try:
            title_el = card_element.find_element(By.XPATH, ".//strong | .//div[contains(@class, 'sc-')]") 
            # This xpath is generic, relying on aria-label is better if available
            link = card_element.find_element(By.TAG_NAME, "a")
            data['Title'] = link.get_attribute("aria-label") or link.text
            if "View " in data['Title']: 
                data['Title'] = data['Title'].replace("View ", "")
        except:
            lines = card_element.text.split('\n')
            if lines: data['Title'] = lines[0]

        # 4. Location (often at the bottom of card)
        # We assume it's one of the last lines
        lines = card_element.text.split('\n')
        for line in lines[-3:]:
            if "," in line or "Remote" in line:
                data['Location'] = line
                break

    except Exception:
        pass # Return whatever partial data we got
        
    return data

def close_modal(driver):
    """Aggressively attempts to close any open modal."""
    # 1. ESC Key
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
    except: pass
    
    # 2. Click X button
    try:
        driver.execute_script("""
            let btns = document.querySelectorAll('button');
            btns.forEach(b => {
                let label = (b.ariaLabel || '').toLowerCase();
                if(label.includes('close') || label.includes('dismiss')) b.click();
            });
        """)
        time.sleep(0.5)
    except: pass

def check_modal_requirements(modal):
    """
    Scans the modal for complexity.
    Returns a list of barriers (e.g. ['Cover Letter', 'Questions']).
    Returns empty list [] if Resume Only.
    """
    barriers = []
    text = modal.text.lower()
    
    # Docs
    if "cover letter" in text: barriers.append("Cover Letter")
    if "transcript" in text: barriers.append("Transcript")
    if "other required documents" in text: barriers.append("Other Docs")
    
    # Inputs
    try:
        inputs = modal.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        for inp in inputs:
            itype = inp.get_attribute("type")
            # Ignore harmless inputs
            if itype in ["hidden", "submit", "button", "file"]: continue
            
            # Stop immediately for these
            if itype in ["radio", "checkbox"]:
                barriers.append("Questions (Checkbox/Radio)")
                break
                
            # Text inputs: Check if it's a search bar (allowed) or a question (block)
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            label = (inp.get_attribute("aria-label") or "").lower()
            
            if "search" in placeholder or "filter" in placeholder: continue
            
            if inp.is_displayed():
                barriers.append("Questions (Text)")
                break
    except: pass
    
    return barriers

# --- MAIN BOT ---

def run_bot():
    csv_path = get_csv_filepath()
    init_csv(csv_path)
    history = load_history(csv_path)
    
    options = Options()
    options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Optimize loading
    options.page_load_strategy = 'eager' 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 5)

    try:
        driver.get("https://app.joinhandshake.com/job-search")
        input("\n[PAUSE] Log in, Filter, and Press ENTER to start...")
        
        while True:
            # 1. PAGE SETUP
            close_modal(driver)
            
            # 2. FIND CARDS
            try:
                # Use the specific data-hook provided in the HTML dump
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-hook^='job-result-card']")))
                cards = driver.find_elements(By.CSS_SELECTOR, "div[data-hook^='job-result-card']")
            except TimeoutException:
                print("[INFO] No cards found. Retrying/Waiting...")
                time.sleep(2)
                continue

            # 3. IDENTIFY NEW JOBS (Pre-processing)
            jobs_to_process = [] # Tuples of (index, job_id, card_element)
            
            print(f"\n[SCAN] Scanning {len(cards)} cards on page...")
            for i, card in enumerate(cards):
                try:
                    # Extract ID purely from DOM attribute (No scraping needed)
                    hook = card.get_attribute("data-hook")
                    if hook and "|" in hook:
                        job_id = hook.split("|")[1].strip()
                        if job_id not in history:
                            jobs_to_process.append(i)
                except StaleElementReferenceException:
                    continue

            print(f"[PLAN] Found {len(jobs_to_process)} new jobs to process.")

            # 4. PROCESS BATCH
            if not jobs_to_process:
                # Pagination
                print("[NAV] Page finished. Going to next...")
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='next page']")
                    if not next_btn.is_enabled():
                        print("[DONE] No more pages.")
                        break
                    
                    # Scroll to button to avoid interception
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                    time.sleep(0.5)
                    next_btn.click()
                    time.sleep(4) # Allow React to fetch new list
                    continue
                except NoSuchElementException:
                    print("[DONE] End of list.")
                    break

            # 5. EXECUTE JOBS
            for index in jobs_to_process:
                # Re-fetch card to avoid StaleElement
                try:
                    current_cards = driver.find_elements(By.CSS_SELECTOR, "div[data-hook^='job-result-card']")
                    if index >= len(current_cards): break
                    card = current_cards[index]
                    
                    # A. EXTRACT DATA (List View)
                    data = get_card_data(card)
                    data['Date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Print current status
                    print(f" -> {data['Company']} | {data['Title']}")

                    # B. CLICK & SYNC
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", card)
                    time.sleep(0.5)
                    try:
                        card.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", card)
                    
                    # Wait for Right Pane
                    time.sleep(1.5) # Hard wait often safer than explicit wait for text sync in React
                    
                    # Update data from Right Pane if possible (Pay, etc)
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, "div[data-hook='right-content']")
                        pane_text = pane.text
                        
                        # Extract Pay/Type if missing
                        if "$" in pane_text:
                            for line in pane_text.split('\n'):
                                if "$" in line: 
                                    data['Pay'] = line
                                    break
                    except: pass

                    # C. CHECK APPLICATION STATUS
                    # 1. Already Applied?
                    if "Applied" in pane_text or "See application" in pane_text:
                        print(f"    [SKIP] Already Applied")
                        data['Status'] = 'Skipped'
                        log_to_csv(csv_path, data)
                        history.add(data['Job ID'])
                        continue

                    # 2. Find Button
                    try:
                        apply_btn = pane.find_element(By.XPATH, ".//button[contains(., 'Apply')]")
                    except NoSuchElementException:
                        # Check for external link text
                        if "Apply externally" in pane_text:
                            print(f"    [SAVE] External Application")
                            data['Status'] = 'External'
                            log_to_csv(csv_path, data)
                            history.add(data['Job ID'])
                            continue
                        else:
                            print(f"    [SKIP] No Apply Button")
                            data['Status'] = 'No Button'
                            log_to_csv(csv_path, data)
                            history.add(data['Job ID'])
                            continue

                    # 3. Check External Button
                    if "external" in apply_btn.text.lower():
                        print(f"    [SAVE] External Link")
                        data['Status'] = 'External'
                        log_to_csv(csv_path, data)
                        history.add(data['Job ID'])
                        continue

                    # D. OPEN MODAL & SCAN
                    apply_btn.click()
                    
                    try:
                        modal = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div[data-hook='apply-modal-content']")))
                        
                        # Scan
                        barriers = check_modal_requirements(modal)
                        
                        if barriers:
                            req_str = ", ".join(barriers)
                            print(f"    [SAVE] Complex: {req_str}")
                            data['Status'] = 'Saved'
                            data['Requirements'] = req_str
                            log_to_csv(csv_path, data)
                            history.add(data['Job ID'])
                            close_modal(driver)
                        else:
                            # E. SUBMIT (Resume Only)
                            try:
                                submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit')]")
                                submit.click()
                                
                                # Wait for success (Modal closes or button disappears)
                                wait.until(EC.staleness_of(submit))
                                print(f"    [SUCCESS] Applied!")
                                data['Status'] = 'APPLIED'
                                data['Requirements'] = 'Resume Only'
                                log_to_csv(csv_path, data)
                                history.add(data['Job ID'])
                                
                                close_modal(driver) # Just in case
                            except Exception as e:
                                print(f"    [FAIL] Submit error: {str(e)[:30]}")
                                data['Status'] = 'Failed'
                                data['Requirements'] = 'Validation Error'
                                log_to_csv(csv_path, data)
                                history.add(data['Job ID'])
                                close_modal(driver)

                    except TimeoutException:
                        print("    [ERR] Modal failed to load")
                        close_modal(driver)

                except Exception as e:
                    print(f"[ERR] Job Loop Error: {str(e)[:50]}")
                    close_modal(driver)
                    continue

    except KeyboardInterrupt:
        print("\n[STOP] User stopped bot.")
    except Exception as e:
        print(f"\n[CRASH] {e}")
    finally:
        print(f"Data saved to: {csv_path}")

if __name__ == "__main__":
    run_bot()