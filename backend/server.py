from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone, timedelta, date, time
import logging
import uuid
import jwt
import bcrypt
import requests
import math

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="ARMI Rental Management")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("armi")

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# Object Storage
# ---------------------------------------------------------------------------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "armi-rental"
storage_key = None


def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="Pengguna tidak ditemukan")
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token kedaluwarsa")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class LoginInput(BaseModel):
    email: str
    password: str


class VehicleInput(BaseModel):
    merek: str
    tipe: str
    tahun: int
    nomor_polisi: str
    warna: str
    harga_per_hari: float
    status: str = "Tersedia"
    catatan: Optional[str] = ""
    foto_url: Optional[str] = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in ("Tersedia", "Disewa", "Maintenance"):
            raise ValueError("Status kendaraan tidak valid")
        return v


class CustomerInput(BaseModel):
    nama: str
    whatsapp: str
    alamat: Optional[str] = ""
    nomor_identitas: Optional[str] = ""
    catatan: Optional[str] = ""


class RentalInput(BaseModel):
    customer_id: str
    vehicle_id: str
    tipe_sewa: str = "Harian"
    tanggal_mulai: str  # YYYY-MM-DD
    tanggal_kembali: str
    waktu_mulai: Optional[str] = None  # HH:MM (24 Jam)
    waktu_kembali: Optional[str] = None
    deposit: float = 0
    status_pembayaran: str = "Belum bayar"
    status_rental: str = "Booking"
    catatan: Optional[str] = ""

    @field_validator("tipe_sewa")
    @classmethod
    def valid_tipe(cls, v):
        if v not in ("Harian", "24 Jam"):
            raise ValueError("Tipe sewa tidak valid")
        return v

    @field_validator("tanggal_mulai", "tanggal_kembali")
    @classmethod
    def valid_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Format tanggal tidak valid (gunakan YYYY-MM-DD)")
        return v

    @field_validator("waktu_mulai", "waktu_kembali")
    @classmethod
    def valid_time(cls, v):
        if v in (None, ""):
            return v
        try:
            datetime.strptime(v, "%H:%M")
        except (ValueError, TypeError):
            raise ValueError("Format waktu tidak valid (gunakan HH:MM)")
        return v


class StatusUpdate(BaseModel):
    status: str


class RentalStatusUpdate(BaseModel):
    status_rental: Optional[str] = None
    status_pembayaran: Optional[str] = None


class RentalUpdate(BaseModel):
    customer_id: str
    vehicle_id: str
    tipe_sewa: str = "Harian"
    tanggal_mulai: str
    tanggal_kembali: str
    waktu_mulai: Optional[str] = None
    waktu_kembali: Optional[str] = None
    harga_per_hari: Optional[float] = None
    catatan: Optional[str] = ""

    @field_validator("tipe_sewa")
    @classmethod
    def valid_tipe(cls, v):
        if v not in ("Harian", "24 Jam"):
            raise ValueError("Tipe sewa tidak valid")
        return v

    @field_validator("tanggal_mulai", "tanggal_kembali")
    @classmethod
    def valid_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Format tanggal tidak valid (gunakan YYYY-MM-DD)")
        return v

    @field_validator("waktu_mulai", "waktu_kembali")
    @classmethod
    def valid_time(cls, v):
        if v in (None, ""):
            return v
        try:
            datetime.strptime(v, "%H:%M")
        except (ValueError, TypeError):
            raise ValueError("Format waktu tidak valid (gunakan HH:MM)")
        return v


class PaymentInput(BaseModel):
    amount: float
    catatan: Optional[str] = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def safe_parse_date(s: str, field: str = "tanggal") -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Format {field} tidak valid (gunakan YYYY-MM-DD)")


async def next_transaksi_id() -> str:
    ym = datetime.now().strftime("%Y%m")
    doc = await db.counters.find_one_and_update(
        {"_id": f"trx-{ym}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return f"TRX-{ym}-{doc['seq']:04d}"


def rental_interval(tipe_sewa, tm, tk, wm=None, wk=None):
    """Return (start_dt, end_dt) occupancy interval for overlap detection."""
    d1 = parse_date(tm)
    d2 = parse_date(tk)
    if tipe_sewa == "24 Jam":
        s = datetime.combine(d1, datetime.strptime(wm or "00:00", "%H:%M").time())
        e = datetime.combine(d2, datetime.strptime(wk or "00:00", "%H:%M").time())
    else:
        # Harian: inclusive calendar days -> occupies through end of tanggal_kembali
        s = datetime.combine(d1, time(0, 0))
        e = datetime.combine(d2, time(0, 0)) + timedelta(days=1)
    return s, e


def compute_rental(vehicle_price, tipe_sewa, tm, tk, wm=None, wk=None):
    if tipe_sewa == "24 Jam":
        s, e = rental_interval("24 Jam", tm, tk, wm, wk)
        hours = (e - s).total_seconds() / 3600
        units = max(math.ceil(hours / 24), 1) if hours > 0 else 1
    else:
        units = max((parse_date(tk) - parse_date(tm)).days + 1, 1)
    subtotal = units * vehicle_price
    return units, subtotal, subtotal


async def date_overlap_exists(vehicle_id, tipe_sewa, tm, tk, wm=None, wk=None, exclude_id=None):
    ns, ne = rental_interval(tipe_sewa, tm, tk, wm, wk)
    query = {"vehicle_id": vehicle_id, "status_rental": {"$in": ["Booking", "Aktif"]}}
    if exclude_id:
        query["id"] = {"$ne": exclude_id}
    existing = await db.rentals.find(query).to_list(1000)
    for r in existing:
        rs, re = rental_interval(
            r.get("tipe_sewa", "Harian"), r["tanggal_mulai"], r["tanggal_kembali"],
            r.get("waktu_mulai"), r.get("waktu_kembali"),
        )
        if ns < re and rs < ne:
            return True
    return False


def compute_payment(total, payments):
    paid = 0.0
    for p in (payments or []):
        try:
            paid += float(p.get("amount", 0) or 0)
        except (TypeError, ValueError):
            continue
    paid = round(paid, 2)
    total = round(total or 0, 2)
    sisa = round(max(total - paid, 0), 2)
    if paid <= 0:
        status = "Belum Dibayar"
    elif paid < total:
        status = "DP / Sebagian"
    else:
        status = "Lunas"
    return paid, sisa, status


async def enrich_rental(r: dict):
    r.pop("_id", None)
    r.setdefault("payments", [])
    paid, sisa, pay_status = compute_payment(r.get("total", 0), r.get("payments"))
    r["total_paid"] = paid
    r["sisa"] = sisa
    r["status_pembayaran"] = pay_status
    cust = await db.customers.find_one({"id": r["customer_id"]}, {"_id": 0})
    veh = await db.vehicles.find_one({"id": r["vehicle_id"]}, {"_id": 0})
    r["customer"] = cust
    r["vehicle"] = veh
    return r


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/login")
async def login(data: LoginInput, request: Request, response: Response):
    email = data.email.lower().strip()
    identifier = email

    attempt = await db.login_attempts.find_one({"identifier": identifier})
    now = datetime.now(timezone.utc)
    if attempt and attempt.get("locked_until"):
        locked_until = datetime.fromisoformat(attempt["locked_until"])
        if locked_until > now:
            raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi dalam 15 menit.")
        # Lock window expired -> reset the counter
        await db.login_attempts.delete_one({"identifier": identifier})
        attempt = None

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        count = (attempt.get("count", 0) if attempt else 0) + 1
        update = {"identifier": identifier, "count": count, "updated_at": now.isoformat()}
        if count >= 5:
            update["locked_until"] = (now + timedelta(minutes=15)).isoformat()
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")

    await db.login_attempts.delete_one({"identifier": identifier})
    token = create_access_token(user["id"], user["email"])
    response.set_cookie(key="access_token", value=token, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user.get("name", "Admin")}}


@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Berhasil keluar"}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", "Admin")}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@api_router.post("/upload")
async def upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(status_code=400, detail="Format gambar tidak didukung")
    path = f"{APP_NAME}/vehicles/{uuid.uuid4()}.{ext}"
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran gambar maksimal 8MB")
    result = put_object(path, data, file.content_type or "image/jpeg")
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "created_at": now_iso(),
    })
    return {"url": f"/api/files/{result['path']}"}


@api_router.get("/files/{path:path}")
async def download_file(path: str):
    record = await db.files.find_one({"storage_path": path})
    if not record:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    data, content_type = get_object(path)
    return Response(content=data, media_type=record.get("content_type", content_type))


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
@api_router.get("/vehicles")
async def list_vehicles(search: Optional[str] = None, status: Optional[str] = None,
                        user: dict = Depends(get_current_user)):
    query = {}
    if status and status != "Semua":
        query["status"] = status
    vehicles = await db.vehicles.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    if search:
        s = search.lower()
        vehicles = [v for v in vehicles if s in v["merek"].lower() or s in v["tipe"].lower()
                    or s in v["nomor_polisi"].lower()]
    return vehicles


@api_router.post("/vehicles")
async def create_vehicle(data: VehicleInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now_iso()
    await db.vehicles.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str, user: dict = Depends(get_current_user)):
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    return v


@api_router.put("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: str, data: VehicleInput, user: dict = Depends(get_current_user)):
    v = await db.vehicles.find_one({"id": vehicle_id})
    if not v:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": data.model_dump()})
    updated = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    return updated


@api_router.patch("/vehicles/{vehicle_id}/status")
async def change_vehicle_status(vehicle_id: str, data: StatusUpdate, user: dict = Depends(get_current_user)):
    if data.status not in ("Tersedia", "Disewa", "Maintenance"):
        raise HTTPException(status_code=400, detail="Status tidak valid")
    res = await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"status": data.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    return await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})


@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str, user: dict = Depends(get_current_user)):
    active = await db.rentals.find_one({"vehicle_id": vehicle_id, "status_rental": {"$in": ["Booking", "Aktif"]}})
    if active:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus: kendaraan memiliki rental aktif")
    res = await db.vehicles.delete_one({"id": vehicle_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    return {"message": "Kendaraan dihapus"}


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@api_router.get("/customers")
async def list_customers(search: Optional[str] = None, user: dict = Depends(get_current_user)):
    customers = await db.customers.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    if search:
        s = search.lower()
        customers = [c for c in customers if s in c["nama"].lower() or s in c["whatsapp"].lower()]
    return customers


@api_router.post("/customers")
async def create_customer(data: CustomerInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now_iso()
    await db.customers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, user: dict = Depends(get_current_user)):
    c = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")
    return c


@api_router.get("/customers/{customer_id}/rentals")
async def customer_rentals(customer_id: str, user: dict = Depends(get_current_user)):
    rentals = await db.rentals.find({"customer_id": customer_id}).sort("created_at", -1).to_list(1000)
    return [await enrich_rental(r) for r in rentals]


@api_router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, data: CustomerInput, user: dict = Depends(get_current_user)):
    res = await db.customers.update_one({"id": customer_id}, {"$set": data.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")
    return await db.customers.find_one({"id": customer_id}, {"_id": 0})


@api_router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, user: dict = Depends(get_current_user)):
    active = await db.rentals.find_one({"customer_id": customer_id, "status_rental": {"$in": ["Booking", "Aktif"]}})
    if active:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus: pelanggan memiliki rental aktif")
    res = await db.customers.delete_one({"id": customer_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")
    return {"message": "Pelanggan dihapus"}


# ---------------------------------------------------------------------------
# Rentals
# ---------------------------------------------------------------------------
async def sync_vehicle_status(vehicle_id: str, rental_status: str):
    if rental_status == "Aktif":
        await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"status": "Disewa"}})
    elif rental_status in ("Selesai", "Dibatalkan"):
        other = await db.rentals.find_one({"vehicle_id": vehicle_id, "status_rental": "Aktif"})
        if not other:
            veh = await db.vehicles.find_one({"id": vehicle_id})
            if veh and veh.get("status") == "Disewa":
                await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"status": "Tersedia"}})


@api_router.get("/rentals")
async def list_rentals(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {}
    if status and status != "Semua":
        query["status_rental"] = status
    rentals = await db.rentals.find(query).sort("created_at", -1).to_list(1000)
    return [await enrich_rental(r) for r in rentals]


@api_router.post("/rentals")
async def create_rental(data: RentalInput, user: dict = Depends(get_current_user)):
    vehicle = await db.vehicles.find_one({"id": data.vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    customer = await db.customers.find_one({"id": data.customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")

    if data.tipe_sewa == "24 Jam":
        if not data.waktu_mulai or not data.waktu_kembali:
            raise HTTPException(status_code=400, detail="Waktu mulai dan berakhir wajib diisi untuk sewa 24 Jam")
        s, e = rental_interval("24 Jam", data.tanggal_mulai, data.tanggal_kembali, data.waktu_mulai, data.waktu_kembali)
        if e <= s:
            raise HTTPException(status_code=400, detail="Waktu berakhir harus setelah waktu mulai")
    else:
        if parse_date(data.tanggal_kembali) < parse_date(data.tanggal_mulai):
            raise HTTPException(status_code=400, detail="Tanggal kembali tidak boleh sebelum tanggal mulai")

    if data.status_rental in ("Booking", "Aktif"):
        if await date_overlap_exists(data.vehicle_id, data.tipe_sewa, data.tanggal_mulai,
                                     data.tanggal_kembali, data.waktu_mulai, data.waktu_kembali):
            raise HTTPException(status_code=409, detail="Booking bentrok! Kendaraan sudah dibooking pada rentang waktu tersebut")

    units, subtotal, total = compute_rental(vehicle["harga_per_hari"], data.tipe_sewa,
                                            data.tanggal_mulai, data.tanggal_kembali,
                                            data.waktu_mulai, data.waktu_kembali)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["transaksi_id"] = await next_transaksi_id()
    doc["harga_per_hari"] = vehicle["harga_per_hari"]
    doc["jumlah_hari"] = units
    doc["subtotal"] = subtotal
    doc["total"] = total
    # Initial deposit becomes the first recorded payment
    payments = []
    if data.deposit and data.deposit > 0:
        payments.append({
            "id": str(uuid.uuid4()),
            "amount": round(min(data.deposit, total), 2),
            "catatan": "DP / Deposit awal",
            "tanggal": now_iso(),
        })
    doc["payments"] = payments
    _, _, doc["status_pembayaran"] = compute_payment(total, payments)
    doc["created_at"] = now_iso()
    await db.rentals.insert_one(doc)
    await sync_vehicle_status(data.vehicle_id, data.status_rental)
    doc.pop("_id", None)
    return await enrich_rental(doc)


async def release_vehicle_if_free(vehicle_id: str):
    other = await db.rentals.find_one({"vehicle_id": vehicle_id, "status_rental": "Aktif"})
    if not other:
        veh = await db.vehicles.find_one({"id": vehicle_id})
        if veh and veh.get("status") == "Disewa":
            await db.vehicles.update_one({"id": vehicle_id}, {"$set": {"status": "Tersedia"}})


@api_router.put("/rentals/{rental_id}")
async def edit_rental(rental_id: str, data: RentalUpdate, user: dict = Depends(get_current_user)):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    vehicle = await db.vehicles.find_one({"id": data.vehicle_id})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    customer = await db.customers.find_one({"id": data.customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")

    if data.tipe_sewa == "24 Jam":
        if not data.waktu_mulai or not data.waktu_kembali:
            raise HTTPException(status_code=400, detail="Waktu mulai dan berakhir wajib diisi untuk sewa 24 Jam")
        s, e = rental_interval("24 Jam", data.tanggal_mulai, data.tanggal_kembali, data.waktu_mulai, data.waktu_kembali)
        if e <= s:
            raise HTTPException(status_code=400, detail="Waktu berakhir harus setelah waktu mulai")
    else:
        if parse_date(data.tanggal_kembali) < parse_date(data.tanggal_mulai):
            raise HTTPException(status_code=400, detail="Tanggal kembali tidak boleh sebelum tanggal mulai")

    # Overlap check only matters for rentals that block availability
    if r["status_rental"] in ("Booking", "Aktif"):
        if await date_overlap_exists(data.vehicle_id, data.tipe_sewa, data.tanggal_mulai,
                                     data.tanggal_kembali, data.waktu_mulai, data.waktu_kembali, exclude_id=rental_id):
            raise HTTPException(status_code=409, detail="Booking bentrok! Kendaraan sudah dibooking pada rentang waktu tersebut")

    harga = data.harga_per_hari if (data.harga_per_hari and data.harga_per_hari > 0) else vehicle["harga_per_hari"]
    units, subtotal, total = compute_rental(harga, data.tipe_sewa, data.tanggal_mulai,
                                            data.tanggal_kembali, data.waktu_mulai, data.waktu_kembali)

    old_vehicle = r["vehicle_id"]
    payments = r.get("payments", [])
    _, _, pay_status = compute_payment(total, payments)

    update = {
        "customer_id": data.customer_id,
        "vehicle_id": data.vehicle_id,
        "tipe_sewa": data.tipe_sewa,
        "tanggal_mulai": data.tanggal_mulai,
        "tanggal_kembali": data.tanggal_kembali,
        "waktu_mulai": data.waktu_mulai,
        "waktu_kembali": data.waktu_kembali,
        "harga_per_hari": harga,
        "jumlah_hari": units,
        "subtotal": subtotal,
        "total": total,
        "status_pembayaran": pay_status,
        "catatan": data.catatan,
    }
    await db.rentals.update_one({"id": rental_id}, {"$set": update})

    # Keep vehicle availability consistent for ACTIVE rentals
    if r["status_rental"] == "Aktif":
        if old_vehicle != data.vehicle_id:
            await release_vehicle_if_free(old_vehicle)
            await db.vehicles.update_one({"id": data.vehicle_id}, {"$set": {"status": "Disewa"}})
        else:
            await db.vehicles.update_one({"id": data.vehicle_id}, {"$set": {"status": "Disewa"}})

    updated = await db.rentals.find_one({"id": rental_id})
    return await enrich_rental(updated)


@api_router.post("/rentals/{rental_id}/payments")
async def add_payment(rental_id: str, data: PaymentInput, user: dict = Depends(get_current_user)):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Jumlah pembayaran harus lebih dari 0")
    paid, sisa, _ = compute_payment(r.get("total", 0), r.get("payments", []))
    if round(data.amount, 2) > sisa:
        raise HTTPException(status_code=400, detail=f"Pembayaran melebihi sisa tagihan (sisa {sisa:.0f})")
    payment = {
        "id": str(uuid.uuid4()),
        "amount": round(data.amount, 2),
        "catatan": data.catatan or "Pembayaran",
        "tanggal": now_iso(),
    }
    payments = r.get("payments", []) + [payment]
    _, _, pay_status = compute_payment(r.get("total", 0), payments)
    await db.rentals.update_one({"id": rental_id}, {"$set": {"payments": payments, "status_pembayaran": pay_status}})
    updated = await db.rentals.find_one({"id": rental_id})
    return await enrich_rental(updated)


@api_router.get("/rentals/{rental_id}")
async def get_rental(rental_id: str, user: dict = Depends(get_current_user)):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    return await enrich_rental(r)


@api_router.patch("/rentals/{rental_id}/status")
async def update_rental_status(rental_id: str, data: RentalStatusUpdate, user: dict = Depends(get_current_user)):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    update = {}
    if data.status_rental:
        if data.status_rental not in ("Booking", "Aktif", "Selesai", "Dibatalkan"):
            raise HTTPException(status_code=400, detail="Status rental tidak valid")
        if data.status_rental in ("Booking", "Aktif") and r["status_rental"] not in ("Booking", "Aktif"):
            if await date_overlap_exists(r["vehicle_id"], r.get("tipe_sewa", "Harian"), r["tanggal_mulai"],
                                         r["tanggal_kembali"], r.get("waktu_mulai"), r.get("waktu_kembali"), exclude_id=rental_id):
                raise HTTPException(status_code=409, detail="Booking bentrok! Kendaraan sudah dibooking pada rentang waktu tersebut")
        update["status_rental"] = data.status_rental
    if update:
        await db.rentals.update_one({"id": rental_id}, {"$set": update})
    if data.status_rental:
        await sync_vehicle_status(r["vehicle_id"], data.status_rental)
    updated = await db.rentals.find_one({"id": rental_id})
    return await enrich_rental(updated)


@api_router.delete("/rentals/{rental_id}")
async def delete_rental(rental_id: str, user: dict = Depends(get_current_user)):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    await db.rentals.delete_one({"id": rental_id})
    await sync_vehicle_status(r["vehicle_id"], "Dibatalkan")
    return {"message": "Rental dihapus"}


# ---------------------------------------------------------------------------
# Invoice PDF (public by rental id so it is shareable)
# ---------------------------------------------------------------------------
def _rupiah(n):
    return "Rp " + f"{int(round(n or 0)):,}".replace(",", ".")


def _fmt_date(s):
    if not s:
        return "-"
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return s


async def build_invoice_pdf(r: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io

    cust = await db.customers.find_one({"id": r["customer_id"]}, {"_id": 0}) or {}
    veh = await db.vehicles.find_one({"id": r["vehicle_id"]}, {"_id": 0}) or {}
    paid, sisa, pay_status = compute_payment(r.get("total", 0), r.get("payments", []))

    blue = colors.HexColor("#2563eb")
    slate = colors.HexColor("#334155")
    muted = colors.HexColor("#94a3b8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=blue, fontSize=20, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=muted, fontSize=9)
    label = ParagraphStyle("label", parent=styles["Normal"], textColor=muted, fontSize=8)
    val = ParagraphStyle("val", parent=styles["Normal"], textColor=slate, fontSize=10)
    sec = ParagraphStyle("sec", parent=styles["Normal"], textColor=slate, fontSize=11, spaceAfter=4, spaceBefore=6, leading=14)

    el = []
    el.append(Paragraph("ARMI Rental Management", h1))
    el.append(Paragraph("ARMI DPD SULSEL", sub))
    el.append(Spacer(1, 8))

    tipe = r.get("tipe_sewa", "Harian")
    if tipe == "24 Jam":
        durasi = f"{r.get('jumlah_hari', 1)} × 24 Jam"
        periode_m = f"{_fmt_date(r['tanggal_mulai'])} {r.get('waktu_mulai') or ''}"
        periode_k = f"{_fmt_date(r['tanggal_kembali'])} {r.get('waktu_kembali') or ''}"
    else:
        durasi = f"{r.get('jumlah_hari', 1)} hari"
        periode_m = _fmt_date(r["tanggal_mulai"])
        periode_k = _fmt_date(r["tanggal_kembali"])

    meta = Table([
        [Paragraph("No. Invoice", label), Paragraph(r.get("transaksi_id", "-"), val),
         Paragraph("Tanggal", label), Paragraph(datetime.now().strftime("%d %b %Y"), val)],
    ], colWidths=[70, 130, 60, 110])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(meta)
    el.append(Spacer(1, 6))
    el.append(Table([[""]], colWidths=[520], style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, blue)])))

    el.append(Paragraph("Pelanggan", sec))
    el.append(Table([
        [Paragraph("Nama", label), Paragraph(cust.get("nama", "-"), val)],
        [Paragraph("WhatsApp", label), Paragraph(cust.get("whatsapp", "-"), val)],
        [Paragraph("Alamat", label), Paragraph(cust.get("alamat", "-") or "-", val)],
    ], colWidths=[80, 440]))

    el.append(Paragraph("Detail Rental", sec))
    el.append(Table([
        [Paragraph("Kendaraan", label), Paragraph(f"{veh.get('merek','')} {veh.get('tipe','')}", val),
         Paragraph("Nomor Polisi", label), Paragraph(veh.get("nomor_polisi", "-"), val)],
        [Paragraph("Tipe Sewa", label), Paragraph(tipe, val),
         Paragraph("Durasi", label), Paragraph(durasi, val)],
        [Paragraph("Mulai", label), Paragraph(periode_m, val),
         Paragraph("Kembali", label), Paragraph(periode_k, val)],
        [Paragraph("Tarif / hari", label), Paragraph(_rupiah(r.get("harga_per_hari", 0)), val), "", ""],
    ], colWidths=[80, 190, 80, 170]))

    el.append(Paragraph("Rincian Pembayaran", sec))
    pay_rows = [[Paragraph("Keterangan", label), Paragraph("Jumlah", label)]]
    pay_rows.append([Paragraph("Subtotal Sewa", val), Paragraph(_rupiah(r.get("subtotal", 0)), val)])
    for p in r.get("payments", []):
        pay_rows.append([Paragraph(f"Dibayar — {p.get('catatan','Pembayaran')} ({_fmt_date(p.get('tanggal',''))})", val),
                         Paragraph("- " + _rupiah(p.get("amount", 0)), val)])
    ptbl = Table(pay_rows, colWidths=[380, 140])
    ptbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, muted),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(ptbl)
    el.append(Spacer(1, 6))

    totals = Table([
        [Paragraph("Grand Total", val), Paragraph(_rupiah(r.get("total", 0)), val)],
        [Paragraph("Sudah Dibayar", val), Paragraph(_rupiah(paid), val)],
        [Paragraph("<b>Sisa Pembayaran</b>", val), Paragraph("<b>" + _rupiah(sisa) + "</b>", val)],
        [Paragraph("Status", val), Paragraph(pay_status, val)],
    ], colWidths=[380, 140])
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, muted),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#eff6ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(totals)

    el.append(Spacer(1, 20))
    el.append(Paragraph("Terima kasih telah mempercayai ARMI Rental. Semoga perjalanan Anda menyenangkan!", sub))
    el.append(Paragraph("Hubungi kami via WhatsApp untuk pertanyaan seputar rental Anda.", sub))

    doc.build(el)
    return buf.getvalue()


@api_router.get("/invoices/{rental_id}")
async def invoice_pdf(rental_id: str):
    r = await db.rentals.find_one({"id": rental_id})
    if not r:
        raise HTTPException(status_code=404, detail="Rental tidak ditemukan")
    pdf = await build_invoice_pdf(r)
    filename = f"Invoice-{r.get('transaksi_id', rental_id)}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={filename}"})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@api_router.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    total_vehicles = len(vehicles)
    tersedia = sum(1 for v in vehicles if v["status"] == "Tersedia")
    disewa = sum(1 for v in vehicles if v["status"] == "Disewa")
    maintenance = sum(1 for v in vehicles if v["status"] == "Maintenance")

    active_bookings = await db.rentals.count_documents({"status_rental": {"$in": ["Booking", "Aktif"]}})

    now = datetime.now(timezone.utc)
    month_start = now.strftime("%Y-%m")
    all_rentals = await db.rentals.find({}, {"_id": 0}).to_list(5000)
    revenue = 0
    outstanding = 0
    for r in all_rentals:
        if r["status_rental"] != "Dibatalkan":
            paid, sisa, _ = compute_payment(r.get("total", 0), r.get("payments", []))
            if r["tanggal_mulai"][:7] == month_start:
                revenue += r.get("total", 0)
            outstanding += sisa

    recent = await db.rentals.find({}).sort("created_at", -1).limit(5).to_list(5)
    recent = [await enrich_rental(r) for r in recent]

    today = date.today()
    returning_today = []
    returning_soon = []
    for r in all_rentals:
        if r["status_rental"] == "Aktif":
            rk = parse_date(r["tanggal_kembali"])
            delta = (rk - today).days
            enriched = await enrich_rental(dict(r))
            if delta == 0:
                returning_today.append(enriched)
            elif 0 < delta <= 3:
                returning_soon.append(enriched)

    # chart: revenue per last 6 months
    chart = []
    for i in range(5, -1, -1):
        m = (now.replace(day=1) - timedelta(days=i * 30))
        key = m.strftime("%Y-%m")
        label = m.strftime("%b")
        total = sum(r.get("total", 0) for r in all_rentals
                    if r["status_rental"] != "Dibatalkan" and r["tanggal_mulai"][:7] == key)
        chart.append({"month": label, "pendapatan": total})

    return {
        "total_vehicles": total_vehicles,
        "tersedia": tersedia,
        "disewa": disewa,
        "maintenance": maintenance,
        "active_bookings": active_bookings,
        "revenue": revenue,
        "outstanding": outstanding,
        "recent": recent,
        "returning_today": returning_today,
        "returning_soon": returning_soon,
        "chart": chart,
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@api_router.get("/reports")
async def reports(start: Optional[str] = None, end: Optional[str] = None,
                  user: dict = Depends(get_current_user)):
    rentals = await db.rentals.find({}, {"_id": 0}).to_list(5000)
    if start and end:
        s = safe_parse_date(start, "start")
        e = safe_parse_date(end, "end")
        rentals = [r for r in rentals if s <= parse_date(r["tanggal_mulai"]) <= e]
    total_rental = len(rentals)
    total_revenue = sum(r.get("total", 0) for r in rentals if r["status_rental"] != "Dibatalkan")
    total_paid = 0
    outstanding = 0
    for r in rentals:
        if r["status_rental"] != "Dibatalkan":
            paid, sisa, _ = compute_payment(r.get("total", 0), r.get("payments", []))
            total_paid += paid
            outstanding += sisa
    aktif = sum(1 for r in rentals if r["status_rental"] == "Aktif")
    selesai = sum(1 for r in rentals if r["status_rental"] == "Selesai")
    dibatalkan = sum(1 for r in rentals if r["status_rental"] == "Dibatalkan")
    return {
        "total_rental": total_rental,
        "total_revenue": total_revenue,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "aktif": aktif,
        "selesai": selesai,
        "dibatalkan": dibatalkan,
    }


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
async def seed():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@armi.id").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": admin_email,
            "password_hash": hash_password(admin_password), "name": "Admin ARMI",
            "role": "admin", "created_at": now_iso(),
        })
        logger.info("Admin user seeded")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    if await db.vehicles.count_documents({}) > 0:
        return

    veh_photos = [
        "https://images.unsplash.com/photo-1596429916858-6f97b5b9cf48?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1569663485392-300558865df0?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1641825877652-23e34a7358fb?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1771211441450-431272859016?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1664783856972-ac9922d7b2d3?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1657459737249-0da225251448?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
        "https://images.unsplash.com/photo-1657884892350-509f7513207d?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    ]
    vehicles = [
        {"merek": "Toyota", "tipe": "Avanza", "tahun": 2022, "nomor_polisi": "B 1234 ABC", "warna": "Silver", "harga_per_hari": 350000, "status": "Tersedia"},
        {"merek": "Toyota", "tipe": "Innova Reborn", "tahun": 2021, "nomor_polisi": "B 5678 DEF", "warna": "Hitam", "harga_per_hari": 550000, "status": "Tersedia"},
        {"merek": "Honda", "tipe": "Brio", "tahun": 2023, "nomor_polisi": "D 9012 GHI", "warna": "Merah", "harga_per_hari": 300000, "status": "Tersedia"},
        {"merek": "Daihatsu", "tipe": "Xenia", "tahun": 2020, "nomor_polisi": "F 3456 JKL", "warna": "Putih", "harga_per_hari": 320000, "status": "Maintenance"},
        {"merek": "Mitsubishi", "tipe": "Pajero Sport", "tahun": 2022, "nomor_polisi": "B 7890 MNO", "warna": "Putih", "harga_per_hari": 850000, "status": "Tersedia"},
        {"merek": "Suzuki", "tipe": "Ertiga", "tahun": 2021, "nomor_polisi": "B 2345 PQR", "warna": "Abu-abu", "harga_per_hari": 380000, "status": "Tersedia"},
        {"merek": "Toyota", "tipe": "Fortuner", "tahun": 2023, "nomor_polisi": "B 6789 STU", "warna": "Hitam", "harga_per_hari": 900000, "status": "Tersedia"},
    ]
    vids = []
    for idx, v in enumerate(vehicles):
        v["id"] = str(uuid.uuid4())
        v["catatan"] = ""
        v["foto_url"] = veh_photos[idx]
        v["created_at"] = now_iso()
        vids.append(v["id"])
    await db.vehicles.insert_many([dict(v) for v in vehicles])

    customers = [
        {"nama": "Budi Santoso", "whatsapp": "081234567890", "alamat": "Jl. Merdeka No. 12, Jakarta", "nomor_identitas": "3171012345670001"},
        {"nama": "Siti Rahmawati", "whatsapp": "082198765432", "alamat": "Jl. Sudirman No. 45, Bandung", "nomor_identitas": "3273024567890002"},
        {"nama": "Ahmad Fauzi", "whatsapp": "085711223344", "alamat": "Jl. Diponegoro No. 8, Surabaya", "nomor_identitas": "3578031122330003"},
        {"nama": "Dewi Lestari", "whatsapp": "087855667788", "alamat": "Jl. Gatot Subroto No. 21, Semarang", "nomor_identitas": "3374045566770004"},
    ]
    cids = []
    for c in customers:
        c["id"] = str(uuid.uuid4())
        c["catatan"] = ""
        c["created_at"] = now_iso()
        cids.append(c["id"])
    await db.customers.insert_many([dict(c) for c in customers])

    today = date.today()

    def ds(offset):
        return (today + timedelta(days=offset)).strftime("%Y-%m-%d")

    rentals_data = [
        {"cid": 0, "vid": 0, "tipe": "Harian", "start": ds(-2), "end": ds(0), "pay": "Lunas", "status": "Aktif", "deposit": 200000},
        {"cid": 1, "vid": 1, "tipe": "24 Jam", "start": ds(-1), "end": ds(0), "wm": "10:00", "wk": "10:00", "pay": "DP", "status": "Aktif", "deposit": 300000},
        {"cid": 2, "vid": 4, "tipe": "Harian", "start": ds(-10), "end": ds(-8), "pay": "Lunas", "status": "Selesai", "deposit": 500000},
        {"cid": 3, "vid": 5, "tipe": "Harian", "start": ds(3), "end": ds(5), "pay": "DP", "status": "Booking", "deposit": 200000},
        {"cid": 0, "vid": 6, "tipe": "24 Jam", "start": ds(-20), "end": ds(-18), "wm": "09:00", "wk": "09:00", "pay": "Lunas", "status": "Selesai", "deposit": 400000},
    ]
    count = 0
    for rd in rentals_data:
        veh = vehicles[rd["vid"]]
        units, subtotal, total = compute_rental(veh["harga_per_hari"], rd["tipe"], rd["start"], rd["end"], rd.get("wm"), rd.get("wk"))
        count += 1
        if rd["pay"] == "Lunas":
            payments = [{"id": str(uuid.uuid4()), "amount": total, "catatan": "Pelunasan", "tanggal": now_iso()}]
        elif rd["pay"] == "DP":
            payments = [{"id": str(uuid.uuid4()), "amount": min(rd["deposit"], total), "catatan": "DP / Deposit awal", "tanggal": now_iso()}]
        else:
            payments = []
        _, _, pay_status = compute_payment(total, payments)
        doc = {
            "id": str(uuid.uuid4()),
            "transaksi_id": f"TRX-{datetime.now().strftime('%Y%m')}-{count:04d}",
            "customer_id": cids[rd["cid"]],
            "vehicle_id": vids[rd["vid"]],
            "tipe_sewa": rd["tipe"],
            "tanggal_mulai": rd["start"],
            "tanggal_kembali": rd["end"],
            "waktu_mulai": rd.get("wm"),
            "waktu_kembali": rd.get("wk"),
            "harga_per_hari": veh["harga_per_hari"],
            "jumlah_hari": units,
            "subtotal": subtotal,
            "deposit": rd["deposit"],
            "payments": payments,
            "total": total,
            "status_pembayaran": pay_status,
            "status_rental": rd["status"],
            "catatan": "",
            "created_at": now_iso(),
        }
        await db.rentals.insert_one(doc)
        if rd["status"] == "Aktif":
            await db.vehicles.update_one({"id": vids[rd["vid"]]}, {"$set": {"status": "Disewa"}})
    ym = datetime.now().strftime("%Y%m")
    await db.counters.update_one({"_id": f"trx-{ym}"}, {"$set": {"seq": count}}, upsert=True)
    logger.info("Sample data seeded")


async def migrate_payments():
    """Add a payments[] array to legacy rentals based on old deposit/status."""
    cursor = db.rentals.find({"payments": {"$exists": False}})
    migrated = 0
    async for r in cursor:
        total = r.get("total", 0)
        old = r.get("status_pembayaran", "")
        deposit = r.get("deposit", 0) or 0
        if old == "Lunas":
            payments = [{"id": str(uuid.uuid4()), "amount": total, "catatan": "Pelunasan", "tanggal": r.get("created_at", now_iso())}]
        elif old in ("DP", "DP / Sebagian") and deposit > 0:
            payments = [{"id": str(uuid.uuid4()), "amount": min(deposit, total), "catatan": "DP / Deposit awal", "tanggal": r.get("created_at", now_iso())}]
        elif deposit > 0:
            payments = [{"id": str(uuid.uuid4()), "amount": min(deposit, total), "catatan": "DP / Deposit awal", "tanggal": r.get("created_at", now_iso())}]
        else:
            payments = []
        _, _, pay_status = compute_payment(total, payments)
        await db.rentals.update_one({"id": r["id"]}, {"$set": {"payments": payments, "status_pembayaran": pay_status}})
        migrated += 1
    if migrated:
        logger.info(f"Migrated payments for {migrated} rentals")


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await seed()
    await migrate_payments()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
