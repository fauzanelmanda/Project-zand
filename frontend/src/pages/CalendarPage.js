import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { formatTanggal, formatRupiah, formatDurasi, formatPeriode } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
const monthNames = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

const statusDot = {
  Booking: "bg-violet-500",
  Aktif: "bg-blue-500",
  Selesai: "bg-emerald-500",
  Dibatalkan: "bg-slate-300",
};

export default function CalendarPage() {
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [vehicleFilter, setVehicleFilter] = useState("Semua");
  const [tipeFilter, setTipeFilter] = useState("Semua");
  const [statusFilter, setStatusFilter] = useState("Semua");

  const { data: rentals = [], isLoading } = useQuery({
    queryKey: ["rentals", "Semua"],
    queryFn: async () => (await api.get("/rentals", { params: { status: "Semua" } })).data,
  });
  const { data: vehicles = [] } = useQuery({
    queryKey: ["vehicles-all"],
    queryFn: async () => (await api.get("/vehicles")).data,
  });

  const active = useMemo(() => rentals.filter((r) => {
    if (r.status_rental === "Dibatalkan") return false;
    if (vehicleFilter !== "Semua" && r.vehicle_id !== vehicleFilter) return false;
    if (tipeFilter !== "Semua" && (r.tipe_sewa || "Harian") !== tipeFilter) return false;
    if (statusFilter !== "Semua" && r.status_rental !== statusFilter) return false;
    return true;
  }), [rentals, vehicleFilter, tipeFilter, statusFilter]);

  const monthActive = useMemo(() => {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const monthStart = `${year}-${String(month + 1).padStart(2, "0")}-01`;
    const lastDay = new Date(year, month + 1, 0).getDate();
    const monthEnd = `${year}-${String(month + 1).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
    return active.filter((r) => r.tanggal_mulai <= monthEnd && r.tanggal_kembali >= monthStart);
  }, [active, cursor]);

  const { days, monthLabel } = useMemo(() => {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < firstDay; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const date = new Date(year, month, d);
      const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const bookings = active.filter((r) => r.tanggal_mulai <= dateStr && dateStr <= r.tanggal_kembali);
      cells.push({ d, dateStr, bookings, isToday: date.toDateString() === new Date().toDateString() });
    }
    return { days: cells, monthLabel: `${monthNames[month]} ${year}` };
  }, [cursor, active]);

  const move = (delta) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + delta, 1));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Kalender Rental</h1>
          <p className="mt-1 text-sm text-slate-500">Jadwal penyewaan kendaraan.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" data-testid="cal-prev" onClick={() => move(-1)}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="min-w-[160px] text-center font-heading font-semibold text-slate-800" data-testid="cal-month">{monthLabel}</span>
          <Button variant="outline" size="icon" data-testid="cal-next" onClick={() => move(1)}><ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Select value={vehicleFilter} onValueChange={setVehicleFilter}>
          <SelectTrigger data-testid="cal-filter-vehicle" className="h-11 sm:w-64"><SelectValue placeholder="Kendaraan" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Semua">Semua Kendaraan</SelectItem>
            {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.merek} {v.tipe} ({v.nomor_polisi})</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={tipeFilter} onValueChange={setTipeFilter}>
          <SelectTrigger data-testid="cal-filter-tipe" className="h-11 sm:w-40"><SelectValue placeholder="Tipe Sewa" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Semua">Semua Tipe</SelectItem>
            <SelectItem value="Harian">Harian</SelectItem>
            <SelectItem value="24 Jam">24 Jam</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger data-testid="cal-filter-status" className="h-11 sm:w-40"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Semua">Semua Status</SelectItem>
            <SelectItem value="Booking">Booking</SelectItem>
            <SelectItem value="Aktif">Aktif</SelectItem>
            <SelectItem value="Selesai">Selesai</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        {Object.entries(statusDot).filter(([k]) => k !== "Dibatalkan").map(([k, v]) => (
          <span key={k} className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-full ${v}`} /> {k}</span>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-96 rounded-xl" />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_2px_10px_rgba(0,0,0,0.03)]">
          <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50">
            {dayNames.map((d) => (
              <div key={d} className="py-2.5 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((cell, i) => (
              <div
                key={i}
                data-testid={cell ? `cal-day-${cell.dateStr}` : undefined}
                className={`min-h-[92px] border-b border-r border-slate-100 p-1.5 ${cell?.isToday ? "bg-blue-50/40" : ""}`}
              >
                {cell && (
                  <>
                    <div className={`mb-1 text-xs font-semibold ${cell.isToday ? "text-blue-600" : "text-slate-500"}`}>{cell.d}</div>
                    <div className="space-y-1">
                      {cell.bookings.slice(0, 3).map((r) => (
                        <div
                          key={r.id}
                          title={`${r.vehicle?.merek} ${r.vehicle?.tipe} - ${r.customer?.nama}`}
                          className="flex items-center gap-1 truncate rounded bg-slate-50 px-1 py-0.5 text-[10px] text-slate-600"
                        >
                          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot[r.status_rental]}`} />
                          <span className="truncate">{r.vehicle?.tipe}</span>
                        </div>
                      ))}
                      {cell.bookings.length > 3 && <div className="px-1 text-[10px] text-slate-400">+{cell.bookings.length - 3} lagi</div>}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming list */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_2px_10px_rgba(0,0,0,0.03)]">
        <div className="mb-4 flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-blue-600" />
          <h2 className="font-heading text-lg font-semibold text-slate-800">Daftar Jadwal</h2>
        </div>
        <div className="space-y-2" data-testid="calendar-list">
          {monthActive.length === 0 && <p className="text-sm text-slate-400">Tidak ada jadwal rental pada bulan ini.</p>}
          {monthActive.map((r) => (
            <div key={r.id} className="flex flex-col gap-2 rounded-lg border border-slate-100 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="font-medium text-slate-800">{r.vehicle?.merek} {r.vehicle?.tipe}</div>
                <div className="text-xs text-slate-500">{r.customer?.nama} · {formatPeriode(r)} · {formatDurasi(r)}</div>
              </div>
              <StatusBadge status={r.status_rental} type="rental" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
