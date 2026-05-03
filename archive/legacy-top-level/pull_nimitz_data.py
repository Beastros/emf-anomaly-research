import requests
import json
import os

# Per project rules: INTERMAGNET HAPI for magnetometer data
HAPI = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
DATE = "2004-11-14"
START = f"{DATE}T00:00:00Z"
STOP  = f"{DATE}T23:59:59Z"
OUT_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer\data\geomag_2004-11-14_FRN_TUC_1sec_definitive"
os.makedirs(OUT_DIR, exist_ok=True)

STATIONS = {
    "FRN": "FRN",
    "TUC": "TUC",
}

def pull_minute(station_id):
    params = {
        "id": f"iaga2002/{station_id}/definitive/PT1M",
        "parameters": "H,D,Z",
        "start": START,
        "stop": STOP,
        "format": "json",
    }
    print(f"Pulling 1-minute data for {station_id}...")
    r = requests.get(HAPI, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

for label, sid in STATIONS.items():
    try:
        data = pull_minute(sid)
        out_path = os.path.join(OUT_DIR, f"{label}_{DATE}_1min_HDZ.json")
        with open(out_path, "w") as f:
            json.dump(data, f)
        print(f"  Saved → {out_path}")
    except Exception as e:
        print(f"  FAILED {label}: {e}")

print("\nDone. Now run nimitz_1sec_analyzer.py")