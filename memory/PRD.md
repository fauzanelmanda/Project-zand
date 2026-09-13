# ARMI Rental Management — PRD

## Problem Statement
Professional Indonesian (Bahasa Indonesia UI) mobile-first web app to manage a car rental business. Functional MVP with real DB, expandable architecture. No customer-facing marketplace — internal rental management only.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor). JWT auth (Bearer token in localStorage + httpOnly cookie fallback). Object storage (Emergent) for vehicle photos.
- Frontend: React 19 + React Router + TanStack Query + Tailwind + shadcn/ui. Light premium theme (Outfit/Manrope fonts, blue accent).
- Collections: users, vehicles, customers, rentals, counters, login_attempts, files.

## User Personas
- Admin rental (single owner/operator) — manages fleet, customers, bookings, reports.

## Core Requirements (static)
- Auth: admin login/logout, protected routes, brute-force lockout (5 fails → 15min).
- Dashboard: 6 stat cards, 6-month revenue chart, recent rentals, returning today/soon.
- Vehicles CRUD: photo upload, search, status filter, status change (Tersedia/Disewa/Maintenance).
- Customers CRUD: rental history, WhatsApp contact.
- Rentals: auto price calc (durasi/subtotal/total), double-booking prevention (409), status (Booking/Aktif/Selesai/Dibatalkan) + payment (Belum bayar/DP/Lunas), vehicle status auto-sync.
- Calendar: month grid + schedule list scoped to displayed month.
- Reports: total rental/pendapatan/aktif/selesai/dibatalkan with Today/Week/Month/Custom filters.
- WhatsApp deep links: konfirmasi booking, pengingat pembayaran, pengingat pengembalian, kontak.

## Implemented (2026-09-10)
- **Combined Rental + Payment filters** on Rental page: existing status pills (Semua/Booking/Aktif/Selesai/Dibatalkan) plus a NEW payment pill row (Semua/Belum Lunas/DP/Lunas). Both combine. Logic (client-side on total_paid/sisa): Belum Lunas = sisa>0, DP = paid>0 & sisa>0, Lunas = sisa==0. Horizontal-scroll compact on mobile.
- **Selesai edit warning**: editing a Selesai rental first shows a confirmation ("⚠️ Transaksi ini sudah selesai…") with Batal / Lanjutkan Edit; edit only opens on Lanjutkan; payment history & transaksi_id preserved. Aktif/Booking edits open directly.
- Verified by testing agent: frontend 100% of scope; backend unchanged (75/76 pytest; the 1 red is a pre-existing seed-dependent vehicle-delete test, not a product defect).

## Implemented (2026-09-07)
- **Edit Rental**: PUT /api/rentals/{id} — change customer, vehicle, tipe sewa, dates/times, tarif per hari, notes; transaksi_id & payment history preserved; overlap re-checked (409); auto-recalc; vehicle availability synced (release old / occupy new on Aktif). UI: Edit button → form prefill → change-summary confirm dialog.
- **Multiple Payments / Sisa Tagihan**: POST /api/rentals/{id}/payments; Total Paid = Σ payments; Sisa = Total − Paid; status auto (Belum Dibayar / DP / Sebagian / Lunas); overpay rejected (400). Shown on rental cards, payment modal, invoice, dashboard "Total Sisa Tagihan" card, reports (Sudah Dibayar + Sisa Tagihan). Legacy rentals backfilled via migrate_payments().
- **Invoice PDF**: public GET /api/invoices/{id} (reportlab) with header ARMI Rental Management / ARMI DPD SULSEL, customer, rental, payment breakdown, grand total/paid/remaining. UI: Invoice button + WhatsApp "Kirim Invoice" (message includes totals + invoice URL).
- **Calendar Filters**: by Vehicle, Rental Type, and Status — combine and update instantly.
- Verified by testing agent: backend 76/76 pytest, frontend 100% of scope, no functional defects.

## Implemented (2026-09-04)
- Rental type **Harian** (inclusive day count, e.g. 1→3 Sep = 3 hari) & **24 Jam** (date+time, exact `N × 24 Jam` = ceil(hours/24)), stored on rental and shown in form/list/calendar/customer history.
- Post-creation confirmation modal: "Order berhasil dibuat" → 🟢 Aktif Sekarang (rental Aktif + vehicle Disewa) or 🔵 Simpan sebagai Booking (vehicle stays Tersedia, dates still locked).
- Booking lifecycle: "Mulai Rental" (Booking→Aktif, vehicle Disewa, data preserved) and "Batalkan" (→Dibatalkan, frees availability, hidden from calendar) with confirm dialogs.
- Double-booking prevention now datetime-interval based, covering Harian, 24 Jam, and MIXED overlaps (409).
- Fixed auth soft-lock: brute-force counter resets after the 15-min window expires. Customer history now shows 24 Jam times via formatPeriode.
- Verified by testing agent: backend 68/68 pytest, frontend 100% of new flows.

## Implemented (2026-08-31)
- Full MVP built and tested end-to-end (backend 44/48 pytest, frontend all core flows).
- Fixed post-test defects: malformed-date validation (400/422), double-booking bypass on status change (409), email-based brute-force lockout (proxy-safe), collision-free transaksi_id (counter collection), calendar month scoping, mobile Sheet a11y title, distinct per-vehicle car photos.
- Sample data auto-seeded: 7 vehicles, 4 customers, 5 rentals.
- Admin: fauzan.elmanda@gmail.com / admin123.

## Backlog / Remaining
- P1: Edit existing rental (dates/customer/vehicle) — only status editable now.
- P2: shadcn Calendar date picker instead of native `<input type=date>`.
- P2: Deposit → remaining balance ("sisa pembayaran") display if deposit reduces amount due.
- P2: Explicit CORS origins; token refresh/revocation.
- P2: Split server.py into routers as it grows.

## Next Tasks
- Await user feedback on MVP; prioritize rental editing and PDF/print invoice.
