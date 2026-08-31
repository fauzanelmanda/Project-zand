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
from datetime import datetime, timezone, timedelta, date
import logging
import uuid
import jwt
import bcrypt
import requests

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
    tanggal_mulai: str  # YYYY-MM-DD
    tanggal_kembali: str
    deposit: float = 0
    status_pembayaran: str = "Belum bayar"
    status_rental: str = "Booking"
    catatan: Optional[str] = ""

    @field_validator("tanggal_mulai", "tanggal_kembali")
    @classmethod
    def valid_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Format tanggal tidak valid (gunakan YYYY-MM-DD)")
        return v


class StatusUpdate(BaseModel):
    status: str


class RentalStatusUpdate(BaseModel):
    status_rental: Optional[str] = None
    status_pembayaran: Optional[str] = None


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


def compute_rental(vehicle_price: float, start: str, end: str, deposit: float):
    d1 = parse_date(start)
    d2 = parse_date(end)
    days = (d2 - d1).days
    if days <= 0:
        days = 1
    subtotal = days * vehicle_price
    total = subtotal
    return days, subtotal, total


async def date_overlap_exists(vehicle_id: str, start: str, end: str, exclude_id: Optional[str] = None):
    s = parse_date(start)
    e = parse_date(end)
    query = {"vehicle_id": vehicle_id, "status_rental": {"$in": ["Booking", "Aktif"]}}
    if exclude_id:
        query["id"] = {"$ne": exclude_id}
    existing = await db.rentals.find(query).to_list(1000)
    for r in existing:
        rs = parse_date(r["tanggal_mulai"])
        re = parse_date(r["tanggal_kembali"])
        # overlap if start < existing_end and existing_start < end
        if s < re and rs < e:
            return True
    return False


async def enrich_rental(r: dict):
    r.pop("_id", None)
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
    if parse_date(data.tanggal_kembali) <= parse_date(data.tanggal_mulai):
        raise HTTPException(status_code=400, detail="Tanggal kembali harus setelah tanggal mulai")
    if data.status_rental in ("Booking", "Aktif"):
        if await date_overlap_exists(data.vehicle_id, data.tanggal_mulai, data.tanggal_kembali):
            raise HTTPException(status_code=409, detail="Booking bentrok! Kendaraan sudah dibooking pada rentang tanggal tersebut")
    days, subtotal, total = compute_rental(vehicle["harga_per_hari"], data.tanggal_mulai, data.tanggal_kembali, data.deposit)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["transaksi_id"] = await next_transaksi_id()
    doc["harga_per_hari"] = vehicle["harga_per_hari"]
    doc["jumlah_hari"] = days
    doc["subtotal"] = subtotal
    doc["total"] = total
    doc["created_at"] = now_iso()
    await db.rentals.insert_one(doc)
    await sync_vehicle_status(data.vehicle_id, data.status_rental)
    doc.pop("_id", None)
    return await enrich_rental(doc)


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
            if await date_overlap_exists(r["vehicle_id"], r["tanggal_mulai"], r["tanggal_kembali"], exclude_id=rental_id):
                raise HTTPException(status_code=409, detail="Booking bentrok! Kendaraan sudah dibooking pada rentang tanggal tersebut")
        update["status_rental"] = data.status_rental
    if data.status_pembayaran:
        if data.status_pembayaran not in ("Belum bayar", "DP", "Lunas"):
            raise HTTPException(status_code=400, detail="Status pembayaran tidak valid")
        update["status_pembayaran"] = data.status_pembayaran
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
    for r in all_rentals:
        if r["status_rental"] != "Dibatalkan" and r["tanggal_mulai"][:7] == month_start:
            revenue += r.get("total", 0)

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
    aktif = sum(1 for r in rentals if r["status_rental"] == "Aktif")
    selesai = sum(1 for r in rentals if r["status_rental"] == "Selesai")
    dibatalkan = sum(1 for r in rentals if r["status_rental"] == "Dibatalkan")
    return {
        "total_rental": total_rental,
        "total_revenue": total_revenue,
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
        {"cid": 0, "vid": 0, "start": ds(-2), "end": ds(0), "pay": "Lunas", "status": "Aktif", "deposit": 200000},
        {"cid": 1, "vid": 1, "start": ds(-1), "end": ds(2), "pay": "DP", "status": "Aktif", "deposit": 300000},
        {"cid": 2, "vid": 4, "start": ds(-10), "end": ds(-7), "pay": "Lunas", "status": "Selesai", "deposit": 500000},
        {"cid": 3, "vid": 5, "start": ds(3), "end": ds(6), "pay": "DP", "status": "Booking", "deposit": 200000},
        {"cid": 0, "vid": 6, "start": ds(-20), "end": ds(-18), "pay": "Lunas", "status": "Selesai", "deposit": 400000},
    ]
    count = 0
    for rd in rentals_data:
        veh = vehicles[rd["vid"]]
        days, subtotal, total = compute_rental(veh["harga_per_hari"], rd["start"], rd["end"], rd["deposit"])
        count += 1
        doc = {
            "id": str(uuid.uuid4()),
            "transaksi_id": f"TRX-{datetime.now().strftime('%Y%m')}-{count:04d}",
            "customer_id": cids[rd["cid"]],
            "vehicle_id": vids[rd["vid"]],
            "tanggal_mulai": rd["start"],
            "tanggal_kembali": rd["end"],
            "harga_per_hari": veh["harga_per_hari"],
            "jumlah_hari": days,
            "subtotal": subtotal,
            "deposit": rd["deposit"],
            "total": total,
            "status_pembayaran": rd["pay"],
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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
