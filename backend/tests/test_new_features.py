"""Iteration 3: PUT /rentals/{id}, POST /rentals/{id}/payments, GET /invoices/{id}."""
import time as _time
import pytest
import requests
from datetime import date, timedelta
from conftest import API


def d2027(offset):
    # far-future dates to avoid seed overlaps
    return (date(2027, 6, 1) + timedelta(days=offset)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def resources(auth_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"})
    vehicles = s.get(f"{API}/vehicles").json()
    customers = s.get(f"{API}/customers").json()
    # use the two oldest seeded free vehicles (Tersedia)
    free = [v for v in vehicles if v["status"] != "Maintenance"]
    v1 = free[-1]
    v2 = free[-2]
    c1 = customers[-1]
    c2 = customers[-2]
    return {"s": s, "v1": v1, "v2": v2, "c1": c1, "c2": c2}


class TestPayments:
    def test_dp_partial_status(self, resources):
        s, v1, c1 = resources["s"], resources["v1"], resources["c1"]
        payload = {"customer_id": c1["id"], "vehicle_id": v1["id"],
                   "tipe_sewa": "Harian", "tanggal_mulai": d2027(0), "tanggal_kembali": d2027(2),
                   "deposit": 200000, "status_rental": "Booking", "catatan": "TEST_dp"}
        r = s.post(f"{API}/rentals", json=payload)
        assert r.status_code == 200, r.text
        rental = r.json()
        try:
            total = rental["total"]
            assert rental["total_paid"] == 200000
            assert rental["sisa"] == total - 200000
            assert rental["status_pembayaran"] == "DP / Sebagian"

            # Add a second payment
            p2 = s.post(f"{API}/rentals/{rental['id']}/payments", json={"amount": 100000, "catatan": "cicilan"})
            assert p2.status_code == 200, p2.text
            d2 = p2.json()
            assert d2["total_paid"] == 300000
            assert d2["sisa"] == total - 300000
            assert d2["status_pembayaran"] == "DP / Sebagian"

            # Overpay rejected
            over = s.post(f"{API}/rentals/{rental['id']}/payments", json={"amount": total})
            assert over.status_code == 400, over.text
            assert "melebihi" in over.json()["detail"].lower()

            # Zero or negative rejected
            neg = s.post(f"{API}/rentals/{rental['id']}/payments", json={"amount": 0})
            assert neg.status_code == 400

            # Pay full remaining -> Lunas
            remaining = d2["sisa"]
            full = s.post(f"{API}/rentals/{rental['id']}/payments", json={"amount": remaining})
            assert full.status_code == 200
            df = full.json()
            assert df["sisa"] == 0
            assert df["total_paid"] == total
            assert df["status_pembayaran"] == "Lunas"
        finally:
            s.delete(f"{API}/rentals/{rental['id']}")


class TestEditRental:
    def test_edit_preserves_transaksi_id_and_customer(self, resources):
        s, v1, c1, c2 = resources["s"], resources["v1"], resources["c1"], resources["c2"]
        r = s.post(f"{API}/rentals", json={
            "customer_id": c1["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(10), "tanggal_kembali": d2027(12),
            "deposit": 0, "status_rental": "Booking"})
        assert r.status_code == 200, r.text
        rental = r.json()
        original_trx = rental["transaksi_id"]
        try:
            upd = s.put(f"{API}/rentals/{rental['id']}", json={
                "customer_id": c2["id"], "vehicle_id": v1["id"],
                "tipe_sewa": "Harian", "tanggal_mulai": d2027(10), "tanggal_kembali": d2027(12)})
            assert upd.status_code == 200, upd.text
            u = upd.json()
            assert u["transaksi_id"] == original_trx
            assert u["customer_id"] == c2["id"]
            # verify persistence
            g = s.get(f"{API}/rentals/{rental['id']}").json()
            assert g["customer_id"] == c2["id"]
            assert g["transaksi_id"] == original_trx
        finally:
            s.delete(f"{API}/rentals/{rental['id']}")

    def test_edit_vehicle_on_aktif_releases_old(self, resources):
        s, v1, v2, c1 = resources["s"], resources["v1"], resources["v2"], resources["c1"]
        # create Aktif rental on v1
        r = s.post(f"{API}/rentals", json={
            "customer_id": c1["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(20), "tanggal_kembali": d2027(22),
            "status_rental": "Aktif"})
        assert r.status_code == 200, r.text
        rental = r.json()
        try:
            assert s.get(f"{API}/vehicles/{v1['id']}").json()["status"] == "Disewa"
            # switch to v2
            upd = s.put(f"{API}/rentals/{rental['id']}", json={
                "customer_id": c1["id"], "vehicle_id": v2["id"],
                "tipe_sewa": "Harian", "tanggal_mulai": d2027(20), "tanggal_kembali": d2027(22)})
            assert upd.status_code == 200, upd.text
            # old vehicle released
            assert s.get(f"{API}/vehicles/{v1['id']}").json()["status"] == "Tersedia"
            assert s.get(f"{API}/vehicles/{v2['id']}").json()["status"] == "Disewa"
        finally:
            s.delete(f"{API}/rentals/{rental['id']}")
            # cleanup: ensure v2 released
            s.patch(f"{API}/vehicles/{v2['id']}/status", json={"status": "Tersedia"})

    def test_edit_type_to_24jam_and_recalc(self, resources):
        s, v1, c1 = resources["s"], resources["v1"], resources["c1"]
        r = s.post(f"{API}/rentals", json={
            "customer_id": c1["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(30), "tanggal_kembali": d2027(32)})
        assert r.status_code == 200, r.text
        rental = r.json()
        try:
            # 3-day Harian
            assert rental["jumlah_hari"] == 3

            upd = s.put(f"{API}/rentals/{rental['id']}", json={
                "customer_id": c1["id"], "vehicle_id": v1["id"],
                "tipe_sewa": "24 Jam", "tanggal_mulai": d2027(30), "tanggal_kembali": d2027(31),
                "waktu_mulai": "10:00", "waktu_kembali": "10:00"})
            assert upd.status_code == 200, upd.text
            u = upd.json()
            assert u["tipe_sewa"] == "24 Jam"
            assert u["jumlah_hari"] == 1
            assert u["total"] == u["harga_per_hari"]

            # Override tarif
            upd2 = s.put(f"{API}/rentals/{rental['id']}", json={
                "customer_id": c1["id"], "vehicle_id": v1["id"],
                "tipe_sewa": "24 Jam", "tanggal_mulai": d2027(30), "tanggal_kembali": d2027(31),
                "waktu_mulai": "10:00", "waktu_kembali": "10:00",
                "harga_per_hari": 999000})
            assert upd2.status_code == 200
            assert upd2.json()["harga_per_hari"] == 999000
            assert upd2.json()["total"] == 999000
        finally:
            s.delete(f"{API}/rentals/{rental['id']}")

    def test_edit_conflict_returns_409(self, resources):
        s, v1, c1, c2 = resources["s"], resources["v1"], resources["c1"], resources["c2"]
        r1 = s.post(f"{API}/rentals", json={
            "customer_id": c1["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(50), "tanggal_kembali": d2027(52),
            "status_rental": "Booking"})
        assert r1.status_code == 200, r1.text
        r2 = s.post(f"{API}/rentals", json={
            "customer_id": c2["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(60), "tanggal_kembali": d2027(62),
            "status_rental": "Booking"})
        assert r2.status_code == 200, r2.text
        try:
            # try to edit r2 into r1's dates -> conflict
            conflict = s.put(f"{API}/rentals/{r2.json()['id']}", json={
                "customer_id": c2["id"], "vehicle_id": v1["id"],
                "tipe_sewa": "Harian", "tanggal_mulai": d2027(50), "tanggal_kembali": d2027(52)})
            assert conflict.status_code == 409, conflict.text
            assert "bentrok" in conflict.json()["detail"].lower()
        finally:
            s.delete(f"{API}/rentals/{r1.json()['id']}")
            s.delete(f"{API}/rentals/{r2.json()['id']}")


class TestInvoice:
    def test_invoice_public_pdf(self, resources):
        s, v1, c1 = resources["s"], resources["v1"], resources["c1"]
        r = s.post(f"{API}/rentals", json={
            "customer_id": c1["id"], "vehicle_id": v1["id"],
            "tipe_sewa": "Harian", "tanggal_mulai": d2027(70), "tanggal_kembali": d2027(71),
            "deposit": 100000, "status_rental": "Booking"})
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        try:
            # unauthenticated - public
            anon = requests.Session()
            g = anon.get(f"{API}/invoices/{rid}", timeout=30)
            assert g.status_code == 200
            assert g.headers.get("content-type", "").startswith("application/pdf")
            assert g.content.startswith(b"%PDF-")
            assert len(g.content) > 1000

            # unknown id
            g404 = anon.get(f"{API}/invoices/does-not-exist", timeout=30)
            assert g404.status_code == 404
        finally:
            s.delete(f"{API}/rentals/{rid}")


class TestDashboardReportsOutstanding:
    def test_dashboard_outstanding_present(self, resources):
        s = resources["s"]
        d = s.get(f"{API}/dashboard").json()
        assert "outstanding" in d
        assert d["outstanding"] >= 0

    def test_reports_paid_and_outstanding(self, resources):
        s = resources["s"]
        rep = s.get(f"{API}/reports").json()
        assert "total_paid" in rep
        assert "outstanding" in rep
        assert rep["total_paid"] >= 0
        assert rep["outstanding"] >= 0
