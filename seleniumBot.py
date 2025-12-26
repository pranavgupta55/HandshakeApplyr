import time
import random
import csv
import os
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    ElementClickInterceptedException, 
    NoSuchElementException, 
    NoSuchWindowException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
# Use the directory where the script is located
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "handshake_data")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

CSV_FILE = os.path.join(DATA_DIR, "application_log.csv")
CHROME_PROFILE = os.path.join(DATA_DIR, "chrome_profile")

# --- LOGGING UTILS ---
def truncate_text(text, max_length=350):
    if not text: return ""
    clean = text.replace('\n', ' ').replace('\r', '').strip()
    return (clean[:max_length] + '...') if len(clean) > max_length else clean

def log_to_csv(data_dict):
    """Logs a dictionary of job data to CSV."""
    file_exists = os.path.isfile(CSV_FILE)
    fieldnames = [
        'Date', 'Status', 'Requirements', 'Company', 'Title', 
        'Pay', 'Job Type', 'Location', 'Company Size', 
        'Job Desc Snippet', 'Company Desc Snippet'
    ]
    
    try:
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            
            # Ensure Date is present
            if 'Date' not in data_dict:
                data_dict['Date'] = time.strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow(data_dict)
    except Exception as e:
        print(f"[ERROR] Could not write to CSV: {e}")

def print_status(company, title, status, color_code):
    # Colors: 92=Green, 93=Yellow, 91=Red, 90=Gray, 0=Reset
    print(f"\033[{color_code}m[{status}] {company} - {title}\033[0m")

# --- BROWSER UTILS ---
def is_browser_alive(driver):
    try:
        driver.title
        return True
    except (NoSuchWindowException, WebDriverException):
        return False

def safe_click(driver, element, wait_time=1.0):
    """
    Tries to click an element. 
    If intercepted (e.g., by a modal), tries to close the modal or force click via JS.
    """
    try:
        # Scroll to center to avoid headers/footers blocking
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.3) # Tiny pause for scroll to settle
        element.click()
    except ElementClickInterceptedException:
        print("[WARN] Click intercepted. Attempting to clear overlays...")
        # Try closing any active dialogs/modals by pressing ESC
        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
        try:
            element.click()
        except:
            # Fallback to JS click
            driver.execute_script("arguments[0].click();", element)
    except Exception as e:
        # Fallback to JS click for other issues
        driver.execute_script("arguments[0].click();", element)
    
    time.sleep(wait_time)

def extract_job_details(right_pane):
    """Scrapes details from the right pane text."""
    details = {
        'Pay': 'N/A', 'Job Type': 'N/A', 'Location': 'N/A',
        'Company Size': 'N/A', 'Job Desc Snippet': 'N/A', 'Company Desc Snippet': 'N/A'
    }
    try:
        text = right_pane.text
        lines = text.split('\n')
        
        # 1. Basic Pay/Type parsing from header area
        for line in lines[:15]:
            if "$" in line: details['Pay'] = line
            if "Internship" in line or "Full-time" in line: details['Job Type'] = line
            if "Remote" in line or ", " in line: # Rough heuristic for location line
                if not details['Location'] or details['Location'] == 'N/A':
                    details['Location'] = line

        # 2. Extract Description (naive)
        details['Job Desc Snippet'] = truncate_text(text, 350)
    except:
        pass
    return details

# --- MAIN BOT ---
def run_bot():
    options = Options()
    options.add_argument(f"user-data-dir={CHROME_PROFILE}") 
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 5)

    try:
        driver.get("https://app.joinhandshake.com/job-search")
        
        print("\n" + "="*50)
        print(f"HANDSHAKE BOT V5 | Data: {DATA_DIR}")
        print("="*50)
        print("1. Log in manually.")
        print("2. Set filters.")
        print("3. Ensure job list is visible.")
        
        input("\nPress ENTER to start...")

        if not is_browser_alive(driver):
            print("[ERROR] Browser closed before start.")
            return

        job_index = 0
        
        while True:
            if not is_browser_alive(driver): break

            # 1. FIND JOB CARDS
            try:
                # Wait for cards to be visible
                wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@data-hook, 'job-result-card')]")))
                job_cards = driver.find_elements(By.XPATH, "//div[contains(@data-hook, 'job-result-card')]")
            except TimeoutException:
                print("[INFO] No job cards found. Page might be loading or empty.")
                job_cards = []

            # PAGINATION CHECK
            if job_index >= len(job_cards):
                print(f"\n--- Page finished. Clicking Next... ---")
                try:
                    next_btn = driver.find_element(By.XPATH, "//button[@aria-label='next page']")
                    if not next_btn.is_enabled():
                        print("[INFO] No more pages (Next button disabled).")
                        break
                    
                    safe_click(driver, next_btn, wait_time=4.0) # Wait for page load
                    job_index = 0
                    continue
                except NoSuchElementException:
                    print("[INFO] No next button found.")
                    break
                except Exception as e:
                    print(f"[ERROR] Pagination failed: {e}")
                    break

            # 2. SELECT JOB CARD
            current_card = job_cards[job_index]
            
            try:
                # Ensure card is visible and clickable
                safe_click(driver, current_card, wait_time=1.5)
                
                # 3. GET RIGHT PANE & DETAILS
                right_pane = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@data-hook='right-content']")))
                
                # Extract Company/Title
                try:
                    company_name = right_pane.find_element(By.XPATH, ".//a[contains(@class, 'employer-name')] | .//div[contains(@class, 'employer-name')]").text
                except: company_name = "Unknown"
                
                try:
                    job_title = right_pane.find_element(By.TAG_NAME, "h1").text
                except: job_title = "Unknown"

                # Extract other details
                details = extract_job_details(right_pane)
                
                record = {
                    'Status': 'Processing',
                    'Company': company_name,
                    'Title': job_title,
                    **details
                }

                # 4. CHECK IF APPLIED / EXTERNAL
                # Check for "Applied" status
                if right_pane.find_elements(By.XPATH, ".//*[contains(text(), 'See application') or contains(text(), 'Applied')]"):
                    print_status(company_name, job_title, "Skipped (Applied)", "90")
                    record['Status'] = 'Skipped'
                    log_to_csv(record)
                    job_index += 1
                    continue

                # Find Apply Button
                apply_btns = right_pane.find_elements(By.XPATH, ".//button[contains(., 'Apply')]")
                
                if not apply_btns:
                    print_status(company_name, job_title, "Skipped (No Button)", "90")
                    record['Status'] = 'Skipped'
                    log_to_csv(record)
                    job_index += 1
                    continue

                apply_btn = apply_btns[0]

                # Check if External
                if "external" in apply_btn.text.lower() or apply_btn.get_attribute("target") == "_blank":
                    print_status(company_name, job_title, "Saved (External)", "93")
                    record['Status'] = 'External'
                    record['Requirements'] = 'External URL'
                    log_to_csv(record)
                    job_index += 1
                    continue

                # 5. OPEN APPLICATION MODAL
                safe_click(driver, apply_btn, wait_time=1.0)

                # Check if modal opened
                try:
                    modal_content = wait.until(EC.visibility_of_element_located((By.XPATH, "//div[@data-hook='apply-modal-content']")))
                    modal_text = modal_content.text.lower()
                except TimeoutException:
                    # Rare: No modal appeared. It might have quick-applied or failed.
                    print_status(company_name, job_title, "Error (No Modal)", "91")
                    # Try to close potential stuck overlays
                    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    job_index += 1
                    continue

                # 6. ANALYZE REQUIREMENTS
                # User Rule: "Only apply to jobs that have just a resume"
                # Reject if: Cover letter, Transcript, Other Documents, or Text Inputs (Questions)
                
                barriers = []
                if "cover letter" in modal_text: barriers.append("Cover Letter")
                if "transcript" in modal_text: barriers.append("Transcript")
                if "other required documents" in modal_text: barriers.append("Other Docs")
                
                # Check for input fields (Questions)
                # We exclude inputs that are file uploads (type='file') or search bars (placeholder contains 'search')
                inputs = modal_content.find_elements(By.XPATH, ".//input[not(@type='file')] | .//textarea")
                for inp in inputs:
                    ph = (inp.get_attribute("placeholder") or "").lower()
                    if "search" not in ph:
                        barriers.append("Questions")
                        break

                if barriers:
                    reqs = ", ".join(barriers)
                    print_status(company_name, job_title, f"Saved ({reqs})", "93")
                    record['Status'] = 'Saved'
                    record['Requirements'] = reqs
                    log_to_csv(record)
                    
                    # Close Modal
                    webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    # Wait for modal to disappear to prevent click interception on next job
                    try:
                        wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[@data-hook='apply-modal-content']")))
                    except: pass
                else:
                    # 7. SUBMIT (Resume Only or No Docs)
                    try:
                        submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit Application')]")
                        safe_click(driver, submit_btn, wait_time=2.0)
                        
                        # Verify Success: Modal should disappear or change to "Application Sent"
                        # We wait for the specific application content to go stale (disappear)
                        try:
                            wait.until(EC.staleness_of(modal_content))
                            print_status(company_name, job_title, "APPLIED", "92")
                            record['Status'] = 'APPLIED'
                            record['Requirements'] = 'Resume Only'
                            log_to_csv(record)
                        except TimeoutException:
                            # Modal stuck open? Force close.
                            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                            print_status(company_name, job_title, "Failed (Stuck)", "91")
                            record['Status'] = 'Failed'
                            log_to_csv(record)

                    except NoSuchElementException:
                        print_status(company_name, job_title, "Error (No Submit Btn)", "91")
                        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()

            except Exception as e:
                # Capture specific error for this job but don't crash loop
                print(f"[ERROR] Job {job_index} error: {str(e)[:100]}")
                # Emergency cleanup: Try to close any open modals
                webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            
            # Increment and pause
            job_index += 1
            time.sleep(random.uniform(1.0, 2.0))

    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")
    except Exception:
        print("\n[CRITICAL CRASH]")
        traceback.print_exc()
    finally:
        print(f"\nLog file: {CSV_FILE}")
        # driver.quit() # Keep open for inspection

if __name__ == "__main__":
    run_bot()