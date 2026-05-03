"""
ScienceBase public JSON API downloader.
Hits catalog/item/{id}?format=json, extracts file download URLs, streams files.
No browser. No Selenium. Pure requests.
"""
import os, sys, json, time
import requests

WORK_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer"

ITEMS = [
    {"id": "628bf1c7d34e4fef2ec3d585", "pattern": "bou2004319", "station": "BOU"},
    {"id": "6334b073d34e900e86c6d5f5", "pattern": "tuc2004319", "station": "TUC"},
    {"id": "6334a9afd34e900e86c6cda0", "pattern": "frn2004319", "station": "FRN"},
]

BASE_ITEM = "https://www.sciencebase.gov/catalog/item"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

def get_item_metadata(item_id):
    url = f"{BASE_ITEM}/{item_id}?format=json"
    print(f"  Metadata: {url}")
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def find_file_url(metadata, pattern):
    """Search the 'files' list in item JSON for a file matching pattern."""
    files = metadata.get("files", [])
    print(f"  Files in item: {len(files)}")
    for f in files:
        name = f.get("name", "")
        url  = f.get("url",  "")
        print(f"    {name}  ->  {url[:80]}")
        if pattern.lower() in name.lower() or pattern.lower() in url.lower():
            return name, url
    return None, None

def download_file(url, dest_path):
    print(f"  Downloading: {url[:80]}")
    r = requests.get(url, headers=HEADERS, stream=True, timeout=120)
    r.raise_for_status()
    total = 0
    with open(dest_path, "wb") as fh:
        for chunk in r.iter_content(65536):
            fh.write(chunk)
            total += len(chunk)
    return total

def main():
    print("=" * 60)
    print("ScienceBase JSON API downloader (no browser)")
    print(f"Target dir: {WORK_DIR}")
    print("=" * 60)

    session_results = []

    for item in ITEMS:
        station = item["station"]
        pattern = item["pattern"]
        item_id = item["id"]

        print(f"\n{'=' * 60}")
        print(f"Station: {station}  |  pattern: {pattern}")

        dest = os.path.join(WORK_DIR, f"{pattern}.raw")
        if os.path.exists(dest):
            sz = os.path.getsize(dest)
            print(f"  [SKIP] Already exists: {dest} ({sz:,} bytes)")
            session_results.append((station, "SKIP", dest))
            continue

        try:
            meta = get_item_metadata(item_id)
        except Exception as e:
            print(f"  [FAIL] Metadata fetch error: {e}")
            session_results.append((station, "META_FAIL", str(e)))
            continue

        fname, furl = find_file_url(meta, pattern)

        if not furl:
            # Dump full metadata for debugging
            print(f"  [WARN] Pattern '{pattern}' not found in files list.")
            print(f"  Full metadata keys: {list(meta.keys())}")
            # Try child items
            children_url = f"{BASE_ITEM}s?parentId={item_id}&format=json"
            print(f"  Trying children: {children_url}")
            try:
                cr = requests.get(children_url, headers=HEADERS, timeout=30)
                cdata = cr.json()
                print(f"  Child items: {json.dumps(cdata, indent=2)[:800]}")
            except Exception as ce:
                print(f"  Children fetch failed: {ce}")
            session_results.append((station, "NOT_FOUND", ""))
            continue

        try:
            nbytes = download_file(furl, dest)
            print(f"  [OK] {os.path.basename(dest)} ({nbytes:,} bytes)")
            session_results.append((station, "OK", dest))
        except Exception as e:
            print(f"  [FAIL] Download error: {e}")
            session_results.append((station, "DL_FAIL", str(e)))

        time.sleep(2)

    print(f"\n{'=' * 60}")
    print("Summary:")
    for station, status, detail in session_results:
        print(f"  {station}: {status}  {os.path.basename(detail) if status == 'OK' else detail}")
    print("=" * 60)
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
