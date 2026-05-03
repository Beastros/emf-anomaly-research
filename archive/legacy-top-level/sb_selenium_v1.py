import time
import os
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

WORK_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer"

ITEMS = [
    {
        "url": "https://www.sciencebase.gov/catalog/item/628bf1c7d34e4fef2ec3d585",
        "pattern": "bou2004319",
        "station": "BOU"
    },
    {
        "url": "https://www.sciencebase.gov/catalog/item/6334b073d34e900e86c6d5f5",
        "pattern": "tuc2004319",
        "station": "TUC"
    },
    {
        "url": "https://www.sciencebase.gov/catalog/item/6334a9afd34e900e86c6cda0",
        "pattern": "frn2004319",
        "station": "FRN"
    }
]

def setup_driver():
    prefs = {
        "download.default_directory": WORK_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    # Try Chrome first
    try:
        opts = ChromeOptions()
        opts.add_experimental_option("prefs", prefs)
        opts.add_argument("--no-sandbox")
        driver = webdriver.Chrome(options=opts)
        print("[OK] Using Chrome")
        return driver
    except Exception as e:
        print(f"[WARN] Chrome failed ({e}), trying Edge...")
    # Try Edge
    try:
        opts = EdgeOptions()
        opts.add_experimental_option("prefs", prefs)
        driver = webdriver.Edge(options=opts)
        print("[OK] Using Edge")
        return driver
    except Exception as e:
        print(f"[FAIL] Edge also failed: {e}")
        raise RuntimeError("Neither Chrome nor Edge Selenium driver found. Install selenium + chromedriver or msedgedriver.")

def find_download_link(driver, pattern):
    """Scan all <a> tags for the target file pattern."""
    links = driver.find_elements(By.TAG_NAME, "a")
    matches = []
    for link in links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if pattern.lower() in href.lower() or pattern.lower() in text.lower():
            matches.append((text, href))
    return matches

def wait_for_file(pattern, timeout=90):
    """Poll WORK_DIR until a file matching pattern is present and fully downloaded."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = glob.glob(os.path.join(WORK_DIR, f"*{pattern}*"))
        files = [f for f in files if not f.endswith(".crdownload") and not f.endswith(".tmp")]
        if files:
            return files[0]
        time.sleep(2)
    return None

def dump_page_links(driver):
    """Print candidate links for manual inspection."""
    links = driver.find_elements(By.TAG_NAME, "a")
    seen = set()
    for link in links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if href and href not in seen and any(kw in href.lower() for kw in ["2004", ".raw", "download", "sciencebase"]):
            seen.add(href)
            print(f"    [{text[:40]}] -> {href[:100]}")

def main():
    print("=" * 60)
    print("ScienceBase 1-second data Selenium downloader")
    print(f"Target dir: {WORK_DIR}")
    print("=" * 60)

    # Install selenium if missing
    try:
        import selenium
    except ImportError:
        print("[INFO] Installing selenium...")
        os.system(r"C:\Users\Mike\AppData\Local\Programs\Python\Python312\python.exe -m pip install selenium")

    driver = setup_driver()
    wait = WebDriverWait(driver, 20)

    try:
        for item in ITEMS:
            station = item["station"]
            pattern = item["pattern"]
            url = item["url"]

            print(f"\n{'=' * 60}")
            print(f"Station: {station}  |  pattern: {pattern}")

            existing = glob.glob(os.path.join(WORK_DIR, f"*{pattern}*"))
            existing = [f for f in existing if not f.endswith(".crdownload")]
            if existing:
                print(f"  [SKIP] Already downloaded: {os.path.basename(existing[0])}")
                continue

            print(f"  Loading: {url}")
            driver.get(url)
            time.sleep(5)  # ScienceBase renders via JS -- give it time
            print(f"  Title: {driver.title[:80]}")

            matches = find_download_link(driver, pattern)

            if matches:
                text, href = matches[0]
                print(f"  [FOUND] {text} -> {href[:80]}")
                # Use JS click to avoid intercept issues
                elem = driver.find_element(By.XPATH, f"//a[contains(@href, '{pattern}') or contains(text(), '{pattern}')]")
                driver.execute_script("arguments[0].click();", elem)
                print(f"  [WAIT] Waiting for download (up to 90s)...")
                result = wait_for_file(pattern)
                if result:
                    size = os.path.getsize(result)
                    print(f"  [OK] {os.path.basename(result)} ({size:,} bytes)")
                else:
                    print(f"  [TIMEOUT] File did not appear -- check browser manually")
            else:
                print(f"  [WARN] Pattern '{pattern}' not found in page links.")
                print(f"  Candidate links on page:")
                dump_page_links(driver)
                print(f"  >>> Browser is open. Download the correct file manually, then press Enter.")
                input()
                result = wait_for_file(pattern, timeout=10)
                if result:
                    print(f"  [OK] Detected: {os.path.basename(result)}")
                else:
                    print(f"  [MISS] Could not confirm download for {station}")

            time.sleep(3)

    finally:
        print("\n[INFO] Keeping browser open 10 s for inspection...")
        time.sleep(10)
        driver.quit()

    # Summary
    print("\n" + "=" * 60)
    print("Download summary:")
    for item in ITEMS:
        found = glob.glob(os.path.join(WORK_DIR, f"*{item['pattern']}*"))
        found = [f for f in found if not f.endswith(".crdownload")]
        status = f"OK  -> {os.path.basename(found[0])}" if found else "MISSING"
        print(f"  {item['station']}: {status}")
    print("=" * 60)
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
