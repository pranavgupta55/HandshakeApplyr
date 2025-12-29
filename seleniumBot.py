import time
import random
import csv
import os
import sys
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "handshake_data")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DEFAULT_CSV_NAME = "application_log.csv"
CHROME_PROFILE = os.path.join(DATA_DIR, "chrome_profile")

# LIMITS
DAILY_LIMIT = 200 

FIELDNAMES = [
    'Job ID', 'Date', 'Status', 'Requirements', 'Company', 'Title', 
    'Job Link', 'Location', 'Pay', 'Job Type'
]

# --- LOGGING HELPER ---
def log_debug(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\033[90m[{timestamp} DEBUG]\033[0m {msg}")

# --- CSV & HISTORY ---

def get_csv_filepath():
    default_path = os.path.join(DATA_DIR, DEFAULT_CSV_NAME)
    if not os.path.exists(default_path): return default_path
    try:
        with open(default_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                headers = next(reader)
                if headers == FIELDNAMES: return default_path
            except StopIteration: return default_path 
    except: pass
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    return processed

def count_applications_last_24h(filepath):
    if not os.path.exists(filepath): return 0
    count = 0
    now = datetime.now()
    one_day_ago = now - timedelta(hours=24)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Status') == 'APPLIED' and row.get('Date'):
                    try:
                        job_date = datetime.strptime(row['Date'], "%Y-%m-%d %H:%M:%S")
                        if job_date > one_day_ago: count += 1
                    except ValueError: pass
    except Exception: pass
    return count

def log_to_csv(filepath, data):
    try:
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            clean = {k: (v if v is not None else "") for k, v in data.items()}
            writer.writerow(clean)
    except Exception as e:
        print(f"[ERROR] CSV Write: {e}")

# --- ROBUST INTERACTION ---

def robust_click(driver, element):
    """
    Tries standard click. If blocked by overlay/modal, forces JS click.
    Returns True if successful, False if element is stale/gone.
    """
    try:
        # Try smooth scroll and click
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.3)
        element.click()
        return True
    except ElementClickInterceptedException:
        # Overlay blocking? JS Click punches through.
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except: return False
    except StaleElementReferenceException:
        return False
    except Exception:
        # Fallback for other issues
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except: return False

def force_clear_overlays(driver):
    """
    Nuclear option: Deletes modal backdrops from DOM.
    """
    # 1. ESC Key
    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    except: pass
    
    # 2. JS: Find and DELETE sticky overlays/modals
    try:
        driver.execute_script("""
            // Click close buttons if available
            document.querySelectorAll('button[aria-label*="close" i], button[aria-label*="dismiss" i], button[aria-label*="Cancel application" i]').forEach(b => b.click());
            
            // Remove modal containers/backdrops directly
            document.querySelectorAll('div[data-hook="apply-modal-content"]').forEach(el => {
                let dialog = el.closest('div[role="dialog"]');
                if(dialog) dialog.remove();
            });
            
            // Remove generic overlays if they are blocking clicks
            document.querySelectorAll('div[class*="modal-overlay"], div[class*="backdrop"]').forEach(el => el.remove());
        """)
    except: pass
    time.sleep(0.5)

# --- DATA EXTRACTION ---

def get_card_data(card_element):
    data = {'Job ID': 'unknown', 'Company': 'Unknown', 'Title': 'Unknown', 'Job Link': '', 'Location': ''}
    try:
        hook = card_element.get_attribute("data-hook")
        if hook and "|" in hook:
            data['Job ID'] = hook.split("|")[1].strip()
            data['Job Link'] = f"https://app.joinhandshake.com/jobs/{data['Job ID']}"

        try:
            img = card_element.find_element(By.TAG_NAME, "img")
            data['Company'] = img.get_attribute("alt")
        except:
            lines = card_element.text.split('\n')
            if len(lines) > 1: data['Company'] = lines[1]

        try:
            link = card_element.find_element(By.TAG_NAME, "a")
            data['Title'] = link.get_attribute("aria-label") or link.text
            if "View " in data['Title']: data['Title'] = data['Title'].replace("View ", "")
        except:
            lines = card_element.text.split('\n')
            if lines: data['Title'] = lines[0]

        lines = card_element.text.split('\n')
        for line in lines[-3:]:
            if "," in line or "Remote" in line:
                data['Location'] = line
                break
    except Exception: pass 
    return data

def check_modal_requirements(modal):
    barriers = []
    text = modal.text.lower()
    
    if "cover letter" in text: barriers.append("Cover Letter")
    if "transcript" in text: barriers.append("Transcript")
    if "other required documents" in text: barriers.append("Other Docs")
    
    try:
        # Check hidden radio/checkboxes
        all_inputs = modal.find_elements(By.TAG_NAME, "input")
        for inp in all_inputs:
            itype = inp.get_attribute("type")
            if itype in ["radio", "checkbox"]:
                barriers.append("Questions (Checkbox/Radio)")
                break
        
        # Check Visible Text Inputs
        inputs = modal.find_elements(By.CSS_SELECTOR, "input, textarea, select")
        for inp in inputs:
            itype = inp.get_attribute("type")
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            label = (inp.get_attribute("aria-label") or "").lower()
            
            if itype in ["hidden", "submit", "button", "file", "radio", "checkbox"]: continue
            
            # Allow resume searches
            if "search" in placeholder or "filter" in placeholder:
                if "resume" not in placeholder and "resume" not in label:
                    barriers.append(f"Document Selector ({placeholder})")
                    break
                else: continue
            
            if inp.is_displayed():
                barriers.append("Questions (Text)")
                break
    except: pass
    
    return barriers

def handle_resume_selection(driver, modal):
    """
    Improved: Explicitly clicks the option in the listbox.
    """
    try:
        resume_inputs = modal.find_elements(By.CSS_SELECTOR, "input[placeholder*='Search your resumes']")
        for inp in resume_inputs:
            if inp.is_displayed():
                current_val = inp.get_attribute("value")
                if not current_val:
                    log_debug("Selecting resume...")
                    robust_click(driver, inp)
                    time.sleep(0.5) # Wait for listbox to appear
                    
                    # Strategy 1: Find the option element
                    try:
                        options = driver.find_elements(By.CSS_SELECTOR, "div[role='option']")
                        if options:
                            robust_click(driver, options[0])
                        else:
                            # Strategy 2: Fallback to Arrow Down
                            inp.send_keys(Keys.ARROW_DOWN)
                            time.sleep(0.2)
                            inp.send_keys(Keys.ENTER)
                    except: 
                        pass

                    # Close dropdown focus
                    try: modal.click()
                    except: pass
    except: pass

def verify_application_success(driver):
    try:
        time.sleep(1.5)
        pane = driver.find_element(By.CSS_SELECTOR, "div[data-hook='right-content']")
        text = pane.text.lower()
        if "withdraw application" in text or "see application" in text or "applied" in text:
            return True
    except: pass
    return False

# --- MAIN BOT ---

def run_bot():
    csv_path = get_csv_filepath()
    init_csv(csv_path)
    history = load_history(csv_path)
    
    applied_24h = count_applications_last_24h(csv_path)
    print(f"\n[LIMIT] Applications in last 24h: {applied_24h} / {DAILY_LIMIT}")
    
    if applied_24h >= DAILY_LIMIT:
        print("[STOP] Daily limit reached.")
        return

    options = Options()
    options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.page_load_strategy = 'eager' 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 5)

    try:
        driver.get("https://app.joinhandshake.com/job-search")
        input("\n[PAUSE] Log in, Filter, and Press ENTER to start...")
        
        while True:
            force_clear_overlays(driver)
            
            try:
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-hook^='job-result-card']")))
                cards = driver.find_elements(By.CSS_SELECTOR, "div[data-hook^='job-result-card']")
            except TimeoutException:
                print("[INFO] No cards found. Retrying...")
                time.sleep(2)
                continue

            jobs_to_process = [] 
            print(f"\n[SCAN] Scanning {len(cards)} cards...")
            for i, card in enumerate(cards):
                try:
                    hook = card.get_attribute("data-hook")
                    if hook and "|" in hook:
                        job_id = hook.split("|")[1].strip()
                        if job_id not in history:
                            jobs_to_process.append(i)
                except StaleElementReferenceException: continue

            print(f"[PLAN] Processing {len(jobs_to_process)} new jobs.")

            # --- PAGINATION ---
            if not jobs_to_process:
                print("[NAV] Page finished. Attempting to click Next...")
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='next page']")
                    if not next_btn.is_enabled():
                        print("[DONE] End.")
                        break
                    
                    if not robust_click(driver, next_btn):
                        # Force JS click if robust failed
                        driver.execute_script("arguments[0].click();", next_btn)
                    
                    time.sleep(5) 
                    continue
                except NoSuchElementException:
                    try:
                        # Fallback Icon Search
                        next_btn = driver.find_element(By.XPATH, "//button[.//svg[contains(@data-icon, 'chevron-right') or contains(@class, 'next')]]")
                        driver.execute_script("arguments[0].click();", next_btn)
                        time.sleep(5)
                        continue
                    except:
                        print("[DONE] No Next button found.")
                        break
                except Exception as e:
                    print(f"[NAV] Pagination Error: {e}. Refreshing...")
                    driver.refresh()
                    time.sleep(5)
                    continue

            # --- JOB LOOP ---
            page_needs_reload = False
            
            for index in jobs_to_process:
                if applied_24h >= DAILY_LIMIT: return

                try:
                    current_cards = driver.find_elements(By.CSS_SELECTOR, "div[data-hook^='job-result-card']")
                    if index >= len(current_cards): break
                    card = current_cards[index]
                    
                    data = get_card_data(card)
                    data['Date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    print(f" -> {data['Company']} | {data['Title']}")

                    # BULLDOZER CLICK
                    if not robust_click(driver, card):
                        log_debug("Card click failed, skipping.")
                        continue
                    
                    time.sleep(1.5)
                    
                    try:
                        pane = driver.find_element(By.CSS_SELECTOR, "div[data-hook='right-content']")
                        pane_text = pane.text
                        if "$" in pane_text:
                            for line in pane_text.split('\n'):
                                if "$" in line: data['Pay'] = line; break
                    except: pane_text = ""

                    if "Applied" in pane_text or "See application" in pane_text:
                        print(f"    [SKIP] Already Applied")
                        data['Status'] = 'Skipped'
                        log_to_csv(csv_path, data)
                        history.add(data['Job ID'])
                        continue

                    try:
                        apply_btn = pane.find_element(By.XPATH, ".//button[contains(., 'Apply')]")
                    except NoSuchElementException:
                        status = 'External' if "Apply externally" in pane_text else 'No Button'
                        print(f"    [SKIP] {status}")
                        data['Status'] = status
                        log_to_csv(csv_path, data)
                        history.add(data['Job ID'])
                        continue

                    if "external" in apply_btn.text.lower():
                        print(f"    [SAVE] External Link")
                        data['Status'] = 'External'
                        log_to_csv(csv_path, data)
                        history.add(data['Job ID'])
                        continue

                    # OPEN MODAL
                    robust_click(driver, apply_btn)
                    
                    try:
                        modal = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div[data-hook='apply-modal-content']")))
                        
                        barriers = check_modal_requirements(modal)
                        if barriers:
                            req_str = ", ".join(barriers)
                            print(f"    [SAVE] Complex: {req_str}")
                            data['Status'] = 'Saved'
                            data['Requirements'] = req_str
                            log_to_csv(csv_path, data)
                            history.add(data['Job ID'])
                            force_clear_overlays(driver)
                        else:
                            handle_resume_selection(driver, modal)
                            
                            try:
                                submit = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'Send')]")
                                
                                if not submit.is_enabled():
                                    print("    [FAIL] Submit Disabled")
                                    data['Status'] = 'Failed'
                                    data['Requirements'] = 'Validation Error (Disabled)'
                                    log_to_csv(csv_path, data)
                                    history.add(data['Job ID'])
                                    force_clear_overlays(driver)
                                    continue

                                robust_click(driver, submit)
                                time.sleep(2.0)
                                
                                force_clear_overlays(driver)
                                
                                if verify_application_success(driver):
                                    print(f"    [SUCCESS] Application Verified!")
                                    data['Status'] = 'APPLIED'
                                    data['Requirements'] = 'Resume Only'
                                    applied_24h += 1
                                else:
                                    print(f"    [FAIL] Validation Error (Not Verified)")
                                    data['Status'] = 'Failed'
                                    data['Requirements'] = 'Validation Error'
                                
                                log_to_csv(csv_path, data)
                                history.add(data['Job ID'])

                            except NoSuchElementException:
                                print("    [FAIL] No Submit Button")
                                force_clear_overlays(driver)

                    except TimeoutException:
                        print("    [ERR] Modal failed to load")
                        force_clear_overlays(driver)

                except Exception as e:
                    print(f"[ERR] Loop Error: {str(e)[:50]}")
                    force_clear_overlays(driver)
                    # If catastrophic error, refresh
                    if "stale" in str(e).lower() or "disconnected" in str(e).lower():
                         driver.refresh()
                         time.sleep(5)
                         page_needs_reload = True
                         break
                    continue
            
            if page_needs_reload:
                continue

    except KeyboardInterrupt:
        print("\n[STOP] User stopped bot.")
    finally:
        print(f"Data saved to: {csv_path}")

if __name__ == "__main__":
    run_bot()