import os, sys, json, subprocess
import urllib.request, urllib.error

def pip(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)
pip("requests")
import requests

WORK_DIR  = r"C:\Users\Mike\uap_sniffer\uap_sniffer"
OUT_1SEC  = os.path.join(WORK_DIR, "null_cache", "1sec")
os.makedirs(OUT_1SEC, exist_ok=True)

# ScienceBase item IDs for USGS 1-second pre-2013 data
# These are the child items under the parent collection 633493e4d34e900e86c6bb21
STATION_ITEMS = {
    "BOU": "628bf1c7d34e4fef2ec3d585",
    "TUC": "6334b073d34e900e86c6d5f5",
    "FRN": "6334a9afd34e900e86c6cda0",
}

SB_API = "https://www.sciencebase.gov/catalog/item"
TARGET_DATE = "2004-11-14"
TARGET_DOY  = 319   # Nov 14 2004 = DOY 319

print()
print("=== USGS 1-Second Magnetometer Downloader ===")
print(f"  Target: {TARGET_DATE} (DOY {TARGET_DOY})")
print(f"  Source: USGS ScienceBase")
print()

def find_and_download(station, item_id):
    print(f"  {station}: Querying ScienceBase item {item_id}...")
    
    # Get item metadata and file list
    url = f"{SB_API}/{item_id}?format=json"
    try:
        r = requests.get(url, timeout=20, 
                        headers={"User-Agent": "Mozilla/5.0 (research)"})
        if r.status_code != 200:
            print(f"    ScienceBase API returned HTTP {r.status_code}")
            return False
        
        data = r.json()
        files = data.get("files", [])
        print(f"    Found {len(files)} files in item")
        
        # Look for 2004 day 319 file
        target_patterns = [
            f"{station.lower()}2004{TARGET_DOY}",
            f"{station.upper()}2004{TARGET_DOY}",
            f"{station.lower()}2004319",
            f"{station.upper()}2004319",
            "2004319",
            "2004318",  # sometimes off by one
        ]
        
        target_file = None
        target_url  = None
        
        for f in files:
            fname = f.get("name", "").lower()
            furl  = f.get("downloadUri", f.get("url", ""))
            for pat in target_patterns:
                if pat.lower() in fname:
                    target_file = f.get("name")
                    target_url  = furl
                    break
            if target_file: break
        
        if not target_file:
            # List available files to help debug
            print(f"    Target file not found. Available files:")
            for f in files[:20]:
                print(f"      {f.get('name','')} -- {f.get('size',0)} bytes")
            if len(files) > 20:
                print(f"      ... and {len(files)-20} more")
            
            # Try child items (data might be organized by year)
            children_url = f"{SB_API}/{item_id}/children?format=json&max=50"
            rc = requests.get(children_url, timeout=20,
                            headers={"User-Agent": "Mozilla/5.0"})
            if rc.status_code == 200:
                children = rc.json().get("items", [])
                print(f"    Found {len(children)} child items")
                for child in children:
                    ctitle = child.get("title", "").lower()
                    if "2004" in ctitle:
                        print(f"    Found 2004 child: {child.get('title')} -- {child.get('id')}")
                        # Recurse into child
                        child_files = child.get("files", [])
                        for f in child_files:
                            fname = f.get("name","").lower()
                            for pat in target_patterns:
                                if pat.lower() in fname:
                                    target_file = f.get("name")
                                    target_url  = f.get("downloadUri", f.get("url",""))
                                    break
                            if target_file: break
                    if target_file: break
            return False
        
        if not target_url:
            print(f"    Found file {target_file} but no download URL")
            return False
        
        # Download the file
        out_path = os.path.join(OUT_1SEC, target_file)
        print(f"    Downloading: {target_file}")
        print(f"    URL: {target_url}")
        
        r2 = requests.get(target_url, timeout=120, stream=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r2.status_code != 200:
            print(f"    Download failed: HTTP {r2.status_code}")
            return False
        
        total = int(r2.headers.get("content-length", 0))
        downloaded = 0
        with open(out_path, "wb") as f:
            for chunk in r2.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
        
        size_mb = os.path.getsize(out_path) / 1e6
        print(f"    Downloaded: {out_path} ({size_mb:.1f} MB)")
        
        # Also copy to working dir for the parser
        import shutil
        dest = os.path.join(WORK_DIR, target_file)
        shutil.copy(out_path, dest)
        print(f"    Copied to: {dest}")
        return True
        
    except Exception as e:
        print(f"    Error: {e}")
        return False

def try_direct_usgs_api(station):
    """Try USGS geomag web service for 1-second historical data."""
    print(f"  {station}: Trying USGS geomag API (1-sec)...")
    url = (f"https://geomag.usgs.gov/ws/data/"
           f"?id={station}&type=variation&elements=D"
           f"&sampling_period=1"
           f"&starttime=2004-11-14T18:45:00Z"
           f"&endtime=2004-11-14T19:47:00Z"
           f"&format=iaga2002")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            content = r.text
            # Check if data is real (not all 99999)
            lines = [l for l in content.splitlines() if not l.startswith("#") and "DATE" not in l and l.strip()]
            valid = 0
            for line in lines[:100]:
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        v = float(parts[3])
                        if v < 99000: valid += 1
                    except: pass
            print(f"    HTTP 200, {len(lines)} data lines, {valid} valid values in first 100")
            if valid > 10:
                out = os.path.join(WORK_DIR, f"{station}20041114_1sec.sec")
                with open(out, "w") as f: f.write(content)
                print(f"    Saved: {out}")
                return True
            else:
                print(f"    All values are missing (99999) -- API doesn't have 2004 1-sec data")
        else:
            print(f"    HTTP {r.status_code}")
    except Exception as e:
        print(f"    Error: {e}")
    return False

print("Attempt 1: USGS geomag API (fastest if it works)")
print("─"*50)
api_success = {}
for sid in STATION_ITEMS:
    api_success[sid] = try_direct_usgs_api(sid)

any_api = any(api_success.values())

if not any_api:
    print()
    print("Attempt 2: ScienceBase direct file download")
    print("─"*50)
    sb_success = {}
    for sid, item_id in STATION_ITEMS.items():
        sb_success[sid] = find_and_download(sid, item_id)

print()
print("="*60)
print("SUMMARY")
print("="*60)
for sid in STATION_ITEMS:
    ok = api_success.get(sid, False) or (not any_api and sb_success.get(sid, False))
    print(f"  {sid}: {'SUCCESS' if ok else 'FAILED'}")

# Check what files landed in working dir
raw_files = [f for f in os.listdir(WORK_DIR)
             if f.endswith(".raw") or f.endswith(".sec")
             if "2004" in f or "1sec" in f]
print()
print(f"  Files in working directory: {raw_files}")

if raw_files:
    print()
    print("  Data files ready. Running parser...")
    parser = os.path.join(WORK_DIR, "nimitz_1sec_parser.py")
    if os.path.exists(parser):
        subprocess.run([sys.executable, parser], cwd=WORK_DIR)
    else:
        print("  Run RUN_1SEC_PARSER.bat to analyze the data")
else:
    print()
    print("  Could not automatically download files.")
    print("  Manual download required:")
    print()
    print("  Open these in browser and look for the 2004 / DOY 319 file:")
    for sid, item_id in STATION_ITEMS.items():
        print(f"  {sid}: https://www.sciencebase.gov/catalog/item/{item_id}")
    print()
    print("  Download the file, copy to:")
    print(f"  {WORK_DIR}")
    print("  Then run RUN_1SEC_PARSER.bat")

print()
input("Press Enter to close...")
