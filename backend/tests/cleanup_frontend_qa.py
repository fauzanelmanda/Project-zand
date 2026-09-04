"""One-off cleanup of rentals created during Playwright UI testing (2027 dates)
and restoration of the seeded vehicle statuses."""
import os
import requests
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"

tok = requests.post(f"{API}/auth/login", json={
    "email": "fauzan.elmanda@gmail.com", "password": "admin123"}, timeout=30).json()["token"]
s = requests.Session()
s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})

rentals = s.get(f"{API}/rentals", timeout=30).json()
removed = 0
for r in rentals:
    if r["tanggal_mulai"].startswith("2027"):
        s.delete(f"{API}/rentals/{r['id']}", timeout=30)
        removed += 1
print("deleted QA rentals:", removed)

# restore seeded vehicle statuses
baseline = {
    "B 1234 ABC": "Disewa", "B 5678 DEF": "Disewa", "D 9012 GHI": "Tersedia",
    "F 3456 JKL": "Maintenance", "B 7890 MNO": "Tersedia", "B 2345 PQR": "Tersedia",
    "B 6789 STU": "Tersedia",
}
for v in s.get(f"{API}/vehicles", timeout=30).json():
    want = baseline.get(v["nomor_polisi"])
    if want and v["status"] != want:
        s.patch(f"{API}/vehicles/{v['id']}/status", json={"status": want}, timeout=30)
        print("reset", v["nomor_polisi"], v["status"], "->", want)

print("remaining rentals:", len(s.get(f"{API}/rentals", timeout=30).json()))
