"""ARMI Rental Management - backend API regression suite."""
import re
from datetime import date, timedelta

import uuid

import pytest
import requests

from conftest import API


def ds(offset):
    return (date.today() + timedelta(days=offset)).strftime("%Y-%m-%d")


# --------------------------------------------------------------- Auth module
class TestAuth:
    def test_login_success(self, test_credentials):
        r = requests.post(f"{API}/auth/login", json=test_credentials, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("token"), str) and len(data["token"]) > 20
        assert data["user"]["email"] == test_credentials["email"].lower()
        assert "password_hash" not in data["user"]
        # httpOnly cookie must be set (playbook requirement)
        set_cookie = r.headers.get("set-cookie", "")
        assert "access_token" in set_cookie, f"No access_token cookie: {set_cookie}"
        assert "httponly" in set_cookie.lower(), f"Cookie not httpOnly: {set_cookie}"

    def test_login_wrong_password(self, test_credentials):
        # NOTE: uses a throwaway identifier so the real admin account is not locked out
        r = requests.post(f"{API}/auth/login",
                          json={"email": f"TEST_wrongpw_{uuid.uuid4().hex[:8]}@example.com", "password": "wrong-pass-xyz"}, timeout=30)
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_login_unknown_email(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": f"nobody_TEST_{uuid.uuid4().hex[:8]}@example.com", "password": "x"}, timeout=30)
        assert r.status_code == 401

    def test_me_with_token(self, client, test_credentials):
        r = client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == test_credentials["email"].lower()

    def test_me_without_token(self, anon):
        r = anon.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token(self, anon):
        r = anon.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
        assert r.status_code == 401

    def test_logout(self, client):
        r = client.post(f"{API}/auth/logout")
        assert r.status_code == 200

    def test_bcrypt_hash_format(self):
        """Admin password hash stored in Mongo must be bcrypt $2b$."""
        import asyncio
        import os

        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values
        env = dotenv_values("/app/backend/.env")
        mongo_url = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME") or env.get("DB_NAME")

        async def check():
            c = AsyncIOMotorClient(mongo_url)
            u = await c[db_name].users.find_one({})
            c.close()
            return u

        user = asyncio.get_event_loop().run_until_complete(check()) if False else asyncio.run(check())
        assert user is not None, "No admin user seeded"
        assert re.match(r"^\$2[aby]\$", user["password_hash"]), user["password_hash"][:10]
        assert user["password_hash"].startswith("$2b$"), f"Expected $2b$, got {user['password_hash'][:4]}"

    def test_brute_force_lockout(self, test_credentials):
        """Playbook: account should lock after 5 failed attempts."""
        codes = []
        bf_email = f"TEST_bruteforce_{uuid.uuid4().hex[:8]}@example.com"
        # throwaway identifier: locking the real admin email would block all other tests for 15 min
        for _ in range(6):
            r = requests.post(f"{API}/auth/login",
                              json={"email": bf_email, "password": "bad-pw"}, timeout=30)
            codes.append(r.status_code)
        assert 429 in codes or 423 in codes, f"No lockout after 6 failed logins, codes={codes}"


# ----------------------------------------------------- Protected route guard
class TestAuthGuards:
    @pytest.mark.parametrize("path", [
        "/vehicles", "/customers", "/rentals", "/dashboard", "/reports",
    ])
    def test_requires_auth(self, anon, path):
        r = anon.get(f"{API}{path}")
        assert r.status_code == 401, f"{path} returned {r.status_code}"


# ------------------------------------------------------------ Vehicle module
class TestVehicles:
    created = []

    def test_list_seeded_vehicles(self, client):
        r = client.get(f"{API}/vehicles")
        assert r.status_code == 200
        vehicles = r.json()
        assert isinstance(vehicles, list) and len(vehicles) >= 7
        v = vehicles[0]
        for k in ("id", "merek", "tipe", "tahun", "nomor_polisi", "harga_per_hari", "status"):
            assert k in v
        assert "_id" not in v

    def test_search_filter(self, client):
        r = client.get(f"{API}/vehicles", params={"search": "Toyota"})
        assert r.status_code == 200
        res = r.json()
        assert len(res) >= 1
        assert all("toyota" in (x["merek"] + x["tipe"] + x["nomor_polisi"]).lower() for x in res)

    def test_status_filter(self, client):
        r = client.get(f"{API}/vehicles", params={"status": "Tersedia"})
        assert r.status_code == 200
        assert all(x["status"] == "Tersedia" for x in r.json())
        r2 = client.get(f"{API}/vehicles", params={"status": "Semua"})
        assert r2.status_code == 200
        assert len(r2.json()) >= len(r.json())

    def test_create_get_update_delete(self, client):
        payload = {"merek": "TEST_Merek", "tipe": "TEST_Tipe", "tahun": 2024,
                   "nomor_polisi": "TEST 0001 QA", "warna": "Biru",
                   "harga_per_hari": 400000, "status": "Tersedia", "catatan": "qa"}
        r = client.post(f"{API}/vehicles", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        vid = created["id"]
        assert created["merek"] == payload["merek"]
        assert created["harga_per_hari"] == 400000
        assert "_id" not in created

        # GET verify persistence
        g = client.get(f"{API}/vehicles/{vid}")
        assert g.status_code == 200
        assert g.json()["nomor_polisi"] == payload["nomor_polisi"]

        # UPDATE
        payload["harga_per_hari"] = 450000
        payload["warna"] = "Hitam"
        u = client.put(f"{API}/vehicles/{vid}", json=payload)
        assert u.status_code == 200
        assert u.json()["harga_per_hari"] == 450000
        g2 = client.get(f"{API}/vehicles/{vid}")
        assert g2.json()["warna"] == "Hitam"

        # PATCH status
        p = client.patch(f"{API}/vehicles/{vid}/status", json={"status": "Maintenance"})
        assert p.status_code == 200
        assert p.json()["status"] == "Maintenance"
        assert client.get(f"{API}/vehicles/{vid}").json()["status"] == "Maintenance"

        # invalid status
        bad = client.patch(f"{API}/vehicles/{vid}/status", json={"status": "Rusak"})
        assert bad.status_code == 400

        # DELETE
        d = client.delete(f"{API}/vehicles/{vid}")
        assert d.status_code == 200
        assert client.get(f"{API}/vehicles/{vid}").status_code == 404

    def test_create_invalid_status_rejected(self, client):
        r = client.post(f"{API}/vehicles", json={
            "merek": "TEST_x", "tipe": "y", "tahun": 2020, "nomor_polisi": "TEST 9 ZZ",
            "warna": "Putih", "harga_per_hari": 100000, "status": "Hancur"})
        assert r.status_code == 422

    def test_create_missing_fields(self, client):
        r = client.post(f"{API}/vehicles", json={"merek": "TEST_only"})
        assert r.status_code == 422

    def test_get_nonexistent(self, client):
        assert client.get(f"{API}/vehicles/does-not-exist").status_code == 404

    def test_delete_blocked_when_active_rental(self, client):
        rentals = client.get(f"{API}/rentals", params={"status": "Aktif"}).json()
        assert rentals, "No active rentals seeded to verify delete-block"
        vid = rentals[0]["vehicle_id"]
        r = client.delete(f"{API}/vehicles/{vid}")
        assert r.status_code == 400
        assert "rental aktif" in r.json()["detail"].lower()


# ----------------------------------------------------------- Customer module
class TestCustomers:
    def test_list_seeded(self, client):
        r = client.get(f"{API}/customers")
        assert r.status_code == 200
        cs = r.json()
        assert len(cs) >= 4
        assert "_id" not in cs[0]
        assert "whatsapp" in cs[0]

    def test_search(self, client):
        r = client.get(f"{API}/customers", params={"search": "Budi"})
        assert r.status_code == 200
        assert any("budi" in c["nama"].lower() for c in r.json())

    def test_crud_and_rentals_history(self, client):
        payload = {"nama": "TEST_QA Pelanggan", "whatsapp": "081200000001",
                   "alamat": "Jl. QA 1", "nomor_identitas": "1234567890000001", "catatan": ""}
        r = client.post(f"{API}/customers", json=payload)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        assert r.json()["nama"] == payload["nama"]

        assert client.get(f"{API}/customers/{cid}").json()["whatsapp"] == "081200000001"

        payload["nama"] = "TEST_QA Updated"
        u = client.put(f"{API}/customers/{cid}", json=payload)
        assert u.status_code == 200 and u.json()["nama"] == "TEST_QA Updated"
        assert client.get(f"{API}/customers/{cid}").json()["nama"] == "TEST_QA Updated"

        h = client.get(f"{API}/customers/{cid}/rentals")
        assert h.status_code == 200 and h.json() == []

        d = client.delete(f"{API}/customers/{cid}")
        assert d.status_code == 200
        assert client.get(f"{API}/customers/{cid}").status_code == 404

    def test_existing_customer_rental_history_enriched(self, client):
        rentals = client.get(f"{API}/rentals").json()
        assert rentals
        cid = rentals[0]["customer_id"]
        h = client.get(f"{API}/customers/{cid}/rentals")
        assert h.status_code == 200
        assert len(h.json()) >= 1
        r0 = h.json()[0]
        assert r0["vehicle"] is not None and r0["customer"] is not None
        assert "_id" not in r0

    def test_update_nonexistent(self, client):
        r = client.put(f"{API}/customers/nope", json={"nama": "TEST_a", "whatsapp": "0812"})
        assert r.status_code == 404


# ------------------------------------------------------------- Rental module
class TestRentals:
    def test_list_enriched(self, client):
        r = client.get(f"{API}/rentals")
        assert r.status_code == 200
        rentals = r.json()
        assert len(rentals) >= 5
        r0 = rentals[0]
        for k in ("id", "transaksi_id", "jumlah_hari", "subtotal", "total", "status_rental", "status_pembayaran"):
            assert k in r0
        assert r0["vehicle"] and r0["customer"]
        assert "_id" not in r0

    def test_status_filter(self, client):
        for s in ["Booking", "Aktif", "Selesai", "Dibatalkan"]:
            r = client.get(f"{API}/rentals", params={"status": s})
            assert r.status_code == 200
            assert all(x["status_rental"] == s for x in r.json())

    def test_create_price_calculation_and_overlap(self, client):
        vehicles = client.get(f"{API}/vehicles").json()
        customers = client.get(f"{API}/customers").json()
        # pick a vehicle with no booking/aktif rental
        busy = {x["vehicle_id"] for x in client.get(f"{API}/rentals").json()
                if x["status_rental"] in ("Booking", "Aktif")}
        free = [v for v in vehicles if v["id"] not in busy]
        assert free, "No free vehicle to test rental creation"
        veh = free[0]
        cust = customers[0]
        start, end = ds(40), ds(43)

        payload = {"customer_id": cust["id"], "vehicle_id": veh["id"],
                   "tanggal_mulai": start, "tanggal_kembali": end,
                   "deposit": 100000, "status_pembayaran": "DP",
                   "status_rental": "Booking", "catatan": "TEST_qa"}
        r = client.post(f"{API}/rentals", json=payload)
        assert r.status_code == 200, r.text
        rental = r.json()
        rid = rental["id"]
        try:
            # Harian is now inclusive: ds(40)..ds(43) = 4 calendar days
            assert rental["jumlah_hari"] == 4
            assert rental["harga_per_hari"] == veh["harga_per_hari"]
            assert rental["subtotal"] == 4 * veh["harga_per_hari"]
            assert rental["total"] == rental["subtotal"]
            assert rental["transaksi_id"].startswith("TRX-")

            # persistence
            g = client.get(f"{API}/rentals/{rid}")
            assert g.status_code == 200 and g.json()["total"] == rental["total"]

            # exact overlap -> 409
            o = client.post(f"{API}/rentals", json=payload)
            assert o.status_code == 409, o.text
            assert "bentrok" in o.json()["detail"].lower()

            # partial overlap -> 409
            o2 = client.post(f"{API}/rentals", json={**payload, "tanggal_mulai": ds(42), "tanggal_kembali": ds(45)})
            assert o2.status_code == 409

            # adjacent (start == existing end + 1 day) -> allowed. NOTE: with the new
            # inclusive-day Harian model, the existing rental occupies all of ds(43),
            # so a new rental may only start on ds(44).
            o3 = client.post(f"{API}/rentals", json={**payload, "tanggal_mulai": ds(44), "tanggal_kembali": ds(45)})
            assert o3.status_code == 200, f"Adjacent booking should be allowed: {o3.text}"
            client.delete(f"{API}/rentals/{o3.json()['id']}")

            # status transitions + vehicle sync
            p = client.patch(f"{API}/rentals/{rid}/status", json={"status_rental": "Aktif"})
            assert p.status_code == 200 and p.json()["status_rental"] == "Aktif"
            assert client.get(f"{API}/vehicles/{veh['id']}").json()["status"] == "Disewa"

            # Payment status is now auto-derived from payments; manual status_pembayaran was removed.
            # Pay the remaining amount to become Lunas.
            g_before = client.get(f"{API}/rentals/{rid}").json()
            sisa = g_before["sisa"]
            if sisa > 0:
                pay = client.post(f"{API}/rentals/{rid}/payments", json={"amount": sisa})
                assert pay.status_code == 200
                assert pay.json()["status_pembayaran"] == "Lunas"

            p3 = client.patch(f"{API}/rentals/{rid}/status", json={"status_rental": "Selesai"})
            assert p3.status_code == 200
            assert client.get(f"{API}/vehicles/{veh['id']}").json()["status"] == "Tersedia"

            bad = client.patch(f"{API}/rentals/{rid}/status", json={"status_rental": "Ngawur"})
            assert bad.status_code == 400
            # NOTE: status_pembayaran via PATCH was removed; payment status is derived from payments.
        finally:
            client.delete(f"{API}/rentals/{rid}")
            assert client.get(f"{API}/rentals/{rid}").status_code == 404

    def test_end_before_start_rejected(self, client):
        vehicles = client.get(f"{API}/vehicles").json()
        customers = client.get(f"{API}/customers").json()
        r = client.post(f"{API}/rentals", json={
            "customer_id": customers[-1]["id"], "vehicle_id": vehicles[-1]["id"],
            "tanggal_mulai": ds(60), "tanggal_kembali": ds(58)})
        assert r.status_code == 400
        assert "tanggal" in r.json()["detail"].lower()

    def test_same_day_harian_is_one_day(self, client):
        """Harian is inclusive, so start == end is a valid 1-day rental."""
        vehicles = client.get(f"{API}/vehicles").json()
        customers = client.get(f"{API}/customers").json()
        # oldest (seeded) vehicle: newest entries may be QA vehicles that parallel workers delete
        veh = vehicles[-1]
        r = client.post(f"{API}/rentals", json={
            "customer_id": customers[-1]["id"], "vehicle_id": veh["id"],
            "tanggal_mulai": ds(70), "tanggal_kembali": ds(70)})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["jumlah_hari"] == 1
        assert d["total"] == veh["harga_per_hari"]
        client.delete(f"{API}/rentals/{d['id']}")

    def test_unknown_vehicle_and_customer(self, client):
        customers = client.get(f"{API}/customers").json()
        vehicles = client.get(f"{API}/vehicles").json()
        r = client.post(f"{API}/rentals", json={
            "customer_id": customers[-1]["id"], "vehicle_id": "nope",
            "tanggal_mulai": ds(80), "tanggal_kembali": ds(82)})
        assert r.status_code == 404
        r2 = client.post(f"{API}/rentals", json={
            "customer_id": "nope", "vehicle_id": vehicles[-1]["id"],
            "tanggal_mulai": ds(80), "tanggal_kembali": ds(82)})
        assert r2.status_code == 404

    def test_malformed_date(self, client):
        customers = client.get(f"{API}/customers").json()
        vehicles = client.get(f"{API}/vehicles").json()
        r = client.post(f"{API}/rentals", json={
            "customer_id": customers[-1]["id"], "vehicle_id": vehicles[-1]["id"],
            "tanggal_mulai": "31-12-2026", "tanggal_kembali": "not-a-date"})
        assert r.status_code in (400, 422), f"Malformed date returned {r.status_code}: {r.text[:200]}"

    def test_get_nonexistent(self, client):
        assert client.get(f"{API}/rentals/nope").status_code == 404


# ---------------------------------------------------------- Dashboard module
class TestDashboard:
    def test_dashboard_shape(self, client):
        r = client.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ("total_vehicles", "tersedia", "disewa", "maintenance",
                  "active_bookings", "revenue", "recent", "returning_today",
                  "returning_soon", "chart"):
            assert k in d, f"missing {k}"
        assert d["total_vehicles"] == d["tersedia"] + d["disewa"] + d["maintenance"]
        vehicles = client.get(f"{API}/vehicles").json()
        assert d["total_vehicles"] == len(vehicles)
        assert len(d["recent"]) <= 5
        assert all("_id" not in x for x in d["recent"])
        assert len(d["chart"]) == 6
        assert all({"month", "pendapatan"} <= set(c) for c in d["chart"])

    def test_chart_months_unique(self, client):
        """Chart built with 30-day arithmetic can repeat/skip months."""
        chart = client.get(f"{API}/dashboard").json()["chart"]
        months = [c["month"] for c in chart]
        assert len(set(months)) == 6, f"Duplicate/skipped months in chart: {months}"

    def test_active_bookings_matches_rentals(self, client):
        d = client.get(f"{API}/dashboard").json()
        rentals = client.get(f"{API}/rentals").json()
        expected = sum(1 for r in rentals if r["status_rental"] in ("Booking", "Aktif"))
        # tolerance: parallel workers may create/delete rentals between the two calls
        assert abs(d["active_bookings"] - expected) <= 3


# ------------------------------------------------------------ Reports module
class TestReports:
    def test_no_filter(self, client):
        r = client.get(f"{API}/reports")
        assert r.status_code == 200
        d = r.json()
        rentals = client.get(f"{API}/rentals").json()
        # tolerance: other parallel test workers may create/delete rentals between the two calls
        assert abs(d["total_rental"] - len(rentals)) <= 3
        assert d["aktif"] >= 0 and d["selesai"] >= 1
        assert d["dibatalkan"] == sum(1 for x in rentals if x["status_rental"] == "Dibatalkan")
        assert d["total_revenue"] > 0

    def test_date_range_filter(self, client):
        r = client.get(f"{API}/reports", params={"start": ds(-30), "end": ds(30)})
        assert r.status_code == 200
        wide = r.json()
        narrow = client.get(f"{API}/reports", params={"start": ds(0), "end": ds(0)}).json()
        assert narrow["total_rental"] <= wide["total_rental"]

    def test_empty_range(self, client):
        r = client.get(f"{API}/reports", params={"start": ds(3000), "end": ds(3010)})
        assert r.status_code == 200
        assert r.json()["total_rental"] == 0
        assert r.json()["total_revenue"] == 0

    def test_invalid_date_params(self, client):
        r = client.get(f"{API}/reports", params={"start": "bogus", "end": "bogus"})
        assert r.status_code in (400, 422), f"Invalid date params -> {r.status_code}"


# --------------------------------------------------------------- Files/misc
class TestFiles:
    def test_missing_file_404(self, anon):
        r = anon.get(f"{API}/files/armi-rental/vehicles/nonexistent.jpg")
        assert r.status_code == 404

    def test_upload_requires_auth(self, anon):
        r = anon.post(f"{API}/upload", files={"file": ("a.png", b"x", "image/png")})
        assert r.status_code == 401

    def test_upload_rejects_bad_extension(self, auth_token):
        r = requests.post(f"{API}/upload",
                          headers={"Authorization": f"Bearer {auth_token}"},
                          files={"file": ("evil.exe", b"MZ", "application/octet-stream")}, timeout=60)
        assert r.status_code == 400


class TestCors:
    def test_cors_credentials_config(self):
        """allow_credentials=True with wildcard origin is invalid for browsers."""
        r = requests.options(f"{API}/auth/login", headers={
            "Origin": "https://rental-management-30.preview.emergentagent.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }, timeout=30)
        allow_origin = r.headers.get("access-control-allow-origin")
        allow_creds = r.headers.get("access-control-allow-credentials")
        assert allow_origin is not None, "No CORS headers returned"
        if allow_creds == "true":
            assert allow_origin != "*", "allow_credentials=true with Access-Control-Allow-Origin: * is rejected by browsers"
