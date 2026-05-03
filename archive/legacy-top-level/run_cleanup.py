import os, sys, shutil

WORK_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer"

# ── Folders to create ─────────────────────────────────────────────────────────
session_dir = os.path.join(WORK_DIR, "session_scripts")
os.makedirs(session_dir, exist_ok=True)

# ── Files to DELETE (numbered duplicates) ─────────────────────────────────────
delete = [
    "claude_code_rules_emfproject (1).txt",
    "emf_project_summary (1).txt",
    "spatial_log",
    "spatial_log.txt",
    "ionex_diag.py",
    "intermagnet_diag.py",
    "deploy_phoenix.py",
    "write_report.py",
    "fix_and_map.py",
]

# ── Files to MOVE to null_cache\ ──────────────────────────────────────────────
to_cache = []
for f in os.listdir(WORK_DIR):
    if any([
        f.startswith("intermagnet_") and f.endswith(".json"),
        f.startswith("mag_") and f.endswith(".json"),
        f.endswith(".i") and f.startswith("jplg"),
        f.endswith(".Z") and any(f.startswith(p) for p in
            ["algo","pie","gold","jplg"]),
    ]):
        to_cache.append(f)

# ── Files to MOVE to session_scripts\ ────────────────────────────────────────
to_session = [
    "install_null.py",
    "install_spatial.py",
    "install_corroborate.py",
    "install_diag.py",
    "install_diag2.py",
    "install_ionex.py",
    "install_patch.py",
    "run_patch_spatial.py",
    "patch_spatial_json.py",
    "RUN_CORROBORATE.bat",
    "RUN_IONEX.bat",
    "RUN_SPATIAL.bat",
    "RUN_DIAG.bat",
    "RUN_DIAG2.bat",
    "phoenix_corroborate.py",
]

# ── Execute ───────────────────────────────────────────────────────────────────
print()
print("=== Directory Cleanup ===")
print()

print("Deleting:")
for f in delete:
    p = os.path.join(WORK_DIR, f)
    if os.path.exists(p):
        os.remove(p)
        print(f"  deleted: {f}")
    else:
        print(f"  skip (not found): {f}")

print()
print("Moving to null_cache:")
cache_dir = os.path.join(WORK_DIR, "null_cache")
os.makedirs(cache_dir, exist_ok=True)
for f in to_cache:
    src = os.path.join(WORK_DIR, f)
    dst = os.path.join(cache_dir, f)
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"  moved: {f}")

print()
print("Moving to session_scripts:")
for f in to_session:
    src = os.path.join(WORK_DIR, f)
    dst = os.path.join(session_dir, f)
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"  moved: {f}")
    else:
        print(f"  skip (not found): {f}")

print()
print("Done. Root directory is now clean.")
print("null_cache\\ holds all cached API data.")
print("session_scripts\\ holds all installer/diagnostic scripts.")
print()
input("Press Enter to close...")
