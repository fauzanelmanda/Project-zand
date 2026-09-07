"""Tests for NEW features: rental type (Harian / 24 Jam), duration math,
double-booking prevention (incl. mixed types) and Booking lifecycle
(Booking -> Aktif via PATCH, Cancel frees availability)."""
import pytest
import requests

from conftest import API

PRICE = 400000
FUT = "2027-06"  # far-future month, no seed data there


@pytest.fixture(scope="module")
def token():
    from conftest import API as _A
    import re
    from pathlib import Path
    c = Path("/app/memory/test_credentials.md").read_text()
    email = re.search(r'(?im)^\s*-?\s*Email\s*:\s*(\S+)', c).group(1)
    pwd = re.search(r'(?im)^\s*-?\s*Password\s*:\s*(\S+)', c).group(1)
    r = requests.post(f"{_A}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code} {r.text[:300]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def fixtures(sess):
    """Dedicated vehicle + customer so overlap tests are isolated."""
    v = sess.post(f"{API}/vehicles", json={
        "merek": "TEST_Merek", "tipe": "TipeSewaQA", "tahun": 2024,
        "nomor_polisi": "QA 24 JAM", "warna": "Biru", "harga_per_hari": PRICE,
        "status": "Tersedia",
    }, timeout=30)
    assert v.status_code == 200, v.text
    veh = v.json()
    c = sess.post(f"{API}/customers", json={
        "nama": "TEST_Pelanggan Tipe", "whatsapp": "081200000099",
    }, timeout=30)
    assert c.status_code == 200, c.text
    cust = c.json()
    created = []
    yield {"vehicle": veh, "customer": cust, "rentals": created}
    for rid in created:
        sess.delete(f"{API}/rentals/{rid}", timeout=30)
    # remove any leftover rentals on this vehicle
    allr = sess.get(f"{API}/rentals", timeout=30).json()
    for r in allr:
        if r["vehicle_id"] == veh["id"]:
            sess.delete(f"{API}/rentals/{r['id']}", timeout=30)
    sess.delete(f"{API}/vehicles/{veh['id']}", timeout=30)
    sess.delete(f"{API}/customers/{cust['id']}", timeout=30)


def mk(fixtures, **kw):
    body = {
        "customer_id": fixtures["customer"]["id"],
        "vehicle_id": fixtures["vehicle"]["id"],
        "tipe_sewa": "Harian",
        "deposit": 0,
        "status_pembayaran": "Belum bayar",
        "status_rental": "Booking",
    }
    body.update(kw)
    return body


# ------------------------------------------------- Harian duration & pricing
class TestHarian:
    def test_inclusive_days_and_total(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=f"{FUT}-01", tanggal_kembali=f"{FUT}-03"), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        fixtures["rentals"].append(d["id"])
        assert d["tipe_sewa"] == "Harian"
        assert d["jumlah_hari"] == 3, d["jumlah_hari"]
        assert d["total"] == 3 * PRICE
        assert d["waktu_mulai"] in (None, "")
        # persisted?
        g = sess.get(f"{API}/rentals/{d['id']}", timeout=30)
        assert g.status_code == 200
        assert g.json()["jumlah_hari"] == 3
        assert g.json()["tipe_sewa"] == "Harian"

    def test_same_day_is_one_day(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=f"{FUT}-20", tanggal_kembali=f"{FUT}-20"), timeout=30)
        assert r.status_code == 200, r.text
        fixtures["rentals"].append(r.json()["id"])
        assert r.json()["jumlah_hari"] == 1
        assert r.json()["total"] == PRICE

    def test_end_before_start_rejected(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=f"{FUT}-10", tanggal_kembali=f"{FUT}-08"), timeout=30)
        assert r.status_code == 400, r.status_code

    def test_booking_keeps_vehicle_tersedia(self, sess, fixtures):
        v = sess.get(f"{API}/vehicles/{fixtures['vehicle']['id']}", timeout=30).json()
        assert v["status"] == "Tersedia", v["status"]

    def test_overlap_harian_409(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=f"{FUT}-02", tanggal_kembali=f"{FUT}-05"), timeout=30)
        assert r.status_code == 409, r.text
        assert "bentrok" in r.json()["detail"].lower()

    def test_no_overlap_next_day_ok(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=f"{FUT}-04", tanggal_kembali=f"{FUT}-05"), timeout=30)
        assert r.status_code == 200, r.text
        fixtures["rentals"].append(r.json()["id"])


# ------------------------------------------------- 24 Jam duration & validation
class Test24Jam:
    def test_exact_24h_is_one_unit(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-11", tanggal_kembali=f"{FUT}-12",
                      waktu_mulai="10:00", waktu_kembali="10:00"), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        fixtures["rentals"].append(d["id"])
        assert d["tipe_sewa"] == "24 Jam"
        assert d["jumlah_hari"] == 1, d["jumlah_hari"]
        assert d["total"] == PRICE
        assert d["waktu_mulai"] == "10:00" and d["waktu_kembali"] == "10:00"

    def test_25h_rounds_up_to_two_units(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-14", tanggal_kembali=f"{FUT}-15",
                      waktu_mulai="08:00", waktu_kembali="09:00"), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        fixtures["rentals"].append(d["id"])
        assert d["jumlah_hari"] == 2, d["jumlah_hari"]
        assert d["total"] == 2 * PRICE

    def test_end_equal_start_rejected(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-16", tanggal_kembali=f"{FUT}-16",
                      waktu_mulai="10:00", waktu_kembali="10:00"), timeout=30)
        assert r.status_code == 400, r.text

    def test_end_before_start_rejected(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-16", tanggal_kembali=f"{FUT}-16",
                      waktu_mulai="12:00", waktu_kembali="09:00"), timeout=30)
        assert r.status_code == 400, r.text

    def test_missing_times_rejected(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-17", tanggal_kembali=f"{FUT}-18"), timeout=30)
        assert r.status_code == 400, r.text

    def test_invalid_tipe_sewa_422(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="Mingguan",
                      tanggal_mulai=f"{FUT}-17", tanggal_kembali=f"{FUT}-18"), timeout=30)
        assert r.status_code == 422, r.status_code

    def test_overlap_24jam_409(self, sess, fixtures):
        # overlaps 11 Jun 10:00 -> 12 Jun 10:00
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-11", tanggal_kembali=f"{FUT}-12",
                      waktu_mulai="20:00", waktu_kembali="20:00"), timeout=30)
        assert r.status_code == 409, r.text

    def test_back_to_back_24jam_allowed(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai=f"{FUT}-12", tanggal_kembali=f"{FUT}-13",
                      waktu_mulai="10:00", waktu_kembali="10:00"), timeout=30)
        assert r.status_code == 200, r.text
        fixtures["rentals"].append(r.json()["id"])


# ------------------------------------------------- Mixed type overlap
class TestMixedOverlap:
    def test_24jam_conflicts_with_harian(self, sess, fixtures):
        base = sess.post(f"{API}/rentals", json=mk(fixtures,
                         tanggal_mulai="2027-07-01", tanggal_kembali="2027-07-03"), timeout=30)
        assert base.status_code == 200, base.text
        fixtures["rentals"].append(base.json()["id"])
        # 24 Jam 2 Jul 10:00 -> 3 Jul 10:00 falls inside the Harian 1-3 Jul block
        r = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                      tanggal_mulai="2027-07-02", tanggal_kembali="2027-07-03",
                      waktu_mulai="10:00", waktu_kembali="10:00"), timeout=30)
        assert r.status_code == 409, r.text

    def test_harian_conflicts_with_24jam(self, sess, fixtures):
        base = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                         tanggal_mulai="2027-08-11", tanggal_kembali="2027-08-12",
                         waktu_mulai="10:00", waktu_kembali="10:00"), timeout=30)
        assert base.status_code == 200, base.text
        fixtures["rentals"].append(base.json()["id"])
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai="2027-08-11", tanggal_kembali="2027-08-11"), timeout=30)
        assert r.status_code == 409, r.text


# ------------------------------------------------- Booking lifecycle
class TestBookingLifecycle:
    def _create_booking(self, sess, fixtures, start, end):
        r = sess.post(f"{API}/rentals", json=mk(fixtures,
                      tanggal_mulai=start, tanggal_kembali=end, deposit=50000,
                      status_pembayaran="DP"), timeout=30)
        assert r.status_code == 200, r.text
        fixtures["rentals"].append(r.json()["id"])
        return r.json()

    def test_booking_to_aktif_syncs_vehicle(self, sess, fixtures):
        b = self._create_booking(sess, fixtures, f"{FUT}-24", f"{FUT}-25")
        assert b["status_rental"] == "Booking"
        p = sess.patch(f"{API}/rentals/{b['id']}/status", json={"status_rental": "Aktif"}, timeout=30)
        assert p.status_code == 200, p.text
        d = p.json()
        assert d["status_rental"] == "Aktif"
        # data preserved
        assert d["customer_id"] == b["customer_id"] and d["vehicle_id"] == b["vehicle_id"]
        assert d["tanggal_mulai"] == b["tanggal_mulai"] and d["tanggal_kembali"] == b["tanggal_kembali"]
        assert d["total"] == b["total"] and d["deposit"] == 50000
        assert d["status_pembayaran"] in ("DP", "DP / Sebagian")
        v = sess.get(f"{API}/vehicles/{fixtures['vehicle']['id']}", timeout=30).json()
        assert v["status"] == "Disewa", v["status"]
        # persisted
        g = sess.get(f"{API}/rentals/{b['id']}", timeout=30).json()
        assert g["status_rental"] == "Aktif"
        # cleanup: finish it so vehicle returns to Tersedia
        sess.patch(f"{API}/rentals/{b['id']}/status", json={"status_rental": "Selesai"}, timeout=30)
        v2 = sess.get(f"{API}/vehicles/{fixtures['vehicle']['id']}", timeout=30).json()
        assert v2["status"] == "Tersedia", v2["status"]

    def test_cancel_frees_availability(self, sess, fixtures):
        b = self._create_booking(sess, fixtures, f"{FUT}-27", f"{FUT}-28")
        # same range must clash while booking is live
        clash = sess.post(f"{API}/rentals", json=mk(fixtures,
                          tanggal_mulai=f"{FUT}-27", tanggal_kembali=f"{FUT}-28"), timeout=30)
        assert clash.status_code == 409, clash.text
        c = sess.patch(f"{API}/rentals/{b['id']}/status", json={"status_rental": "Dibatalkan"}, timeout=30)
        assert c.status_code == 200, c.text
        assert c.json()["status_rental"] == "Dibatalkan"
        ok = sess.post(f"{API}/rentals", json=mk(fixtures,
                       tanggal_mulai=f"{FUT}-27", tanggal_kembali=f"{FUT}-28"), timeout=30)
        assert ok.status_code == 200, ok.text
        fixtures["rentals"].append(ok.json()["id"])
        # reactivating the cancelled one must now be blocked (overlap re-check)
        re_act = sess.patch(f"{API}/rentals/{b['id']}/status", json={"status_rental": "Aktif"}, timeout=30)
        assert re_act.status_code == 409, f"expected 409, got {re_act.status_code}: {re_act.text[:200]}"

    def test_create_aktif_sets_vehicle_disewa(self, sess, fixtures):
        r = sess.post(f"{API}/rentals", json=mk(fixtures, status_rental="Aktif",
                      tanggal_mulai=f"{FUT}-06", tanggal_kembali=f"{FUT}-07"), timeout=30)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        fixtures["rentals"].append(rid)
        assert r.json()["status_rental"] == "Aktif"
        v = sess.get(f"{API}/vehicles/{fixtures['vehicle']['id']}", timeout=30).json()
        assert v["status"] == "Disewa", v["status"]
        sess.patch(f"{API}/rentals/{rid}/status", json={"status_rental": "Selesai"}, timeout=30)

    def test_customer_history_includes_type(self, sess, fixtures):
        r24 = sess.post(f"{API}/rentals", json=mk(fixtures, tipe_sewa="24 Jam",
                        tanggal_mulai="2027-09-05", tanggal_kembali="2027-09-06",
                        waktu_mulai="09:00", waktu_kembali="09:00"), timeout=30)
        assert r24.status_code == 200, r24.text
        fixtures["rentals"].append(r24.json()["id"])
        h = sess.get(f"{API}/customers/{fixtures['customer']['id']}/rentals", timeout=30)
        assert h.status_code == 200
        data = h.json()
        assert len(data) > 0
        assert all("tipe_sewa" in r and "jumlah_hari" in r for r in data)
        assert any(r["tipe_sewa"] == "24 Jam" for r in data)
        assert all("_id" not in r for r in data)
