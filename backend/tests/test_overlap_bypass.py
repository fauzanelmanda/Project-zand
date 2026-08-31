"""Verifies whether PATCH /rentals/{id}/status re-validates double-booking."""
from datetime import date, timedelta

from conftest import API


def ds(o):
    return (date.today() + timedelta(days=o)).strftime("%Y-%m-%d")


class TestOverlapBypassViaStatusPatch:
    def test_reactivating_cancelled_rental_can_double_book(self, client):
        vehicles = client.get(f"{API}/vehicles").json()
        customers = client.get(f"{API}/customers").json()
        busy = {x["vehicle_id"] for x in client.get(f"{API}/rentals").json()
                if x["status_rental"] in ("Booking", "Aktif")}
        veh = [v for v in vehicles if v["id"] not in busy][0]
        base = {"customer_id": customers[0]["id"], "vehicle_id": veh["id"],
                "tanggal_mulai": ds(120), "tanggal_kembali": ds(123),
                "status_rental": "Dibatalkan", "catatan": "TEST_bypass"}
        r1 = client.post(f"{API}/rentals", json=base)
        assert r1.status_code == 200, r1.text
        id1 = r1.json()["id"]

        r2 = client.post(f"{API}/rentals", json={**base, "status_rental": "Booking"})
        assert r2.status_code == 200, r2.text
        id2 = r2.json()["id"]
        try:
            # Reactivate the cancelled one -> overlaps with the active booking
            p = client.patch(f"{API}/rentals/{id1}/status", json={"status_rental": "Aktif"})
            assert p.status_code == 409, (
                f"BUG: status change to Aktif accepted ({p.status_code}) even though it now "
                f"double-books the vehicle for the same dates")
        finally:
            client.delete(f"{API}/rentals/{id1}")
            client.delete(f"{API}/rentals/{id2}")
