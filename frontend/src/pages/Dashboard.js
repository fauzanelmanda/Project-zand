import React from "react";
import { useQuery } from "@tanstack/react-query";
import api, { mediaUrl } from "@/lib/api";
import { formatRupiah, formatTanggal } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Car,
  CheckCircle2,
  KeyRound,
  Wrench,
  CalendarClock,
  Wallet,
  Clock,
  AlertCircle,
} from "lucide-react";
import {
  BarChart,
  Bar,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const StatCard = ({ icon: Icon, label, value, tint, testid }) => (
  <div
    data-testid={testid}
    className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_2px_10px_rgba(0,0,0,0.03)] transition-transform duration-200 hover:-translate-y-1"
  >
    <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-lg ${tint}`}>
      <Icon className="h-5 w-5" />
    </div>
    <div className="text-2xl font-bold tracking-tight text-slate-900">{value}</div>
    <div className="mt-0.5 text-sm text-slate-500">{label}</div>
  </div>
);

export default function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.get("/dashboard")).data,
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Beranda</h1>
        <p className="mt-1 text-sm text-slate-500">Ringkasan operasional rental Anda hari ini.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-4">
        <StatCard testid="stat-total-vehicles" icon={Car} label="Total Kendaraan" value={data.total_vehicles} tint="bg-slate-100 text-slate-700" />
        <StatCard testid="stat-tersedia" icon={CheckCircle2} label="Tersedia" value={data.tersedia} tint="bg-emerald-50 text-emerald-600" />
        <StatCard testid="stat-disewa" icon={KeyRound} label="Sedang Disewa" value={data.disewa} tint="bg-blue-50 text-blue-600" />
        <StatCard testid="stat-maintenance" icon={Wrench} label="Maintenance" value={data.maintenance} tint="bg-amber-50 text-amber-600" />
        <StatCard testid="stat-active-bookings" icon={CalendarClock} label="Booking Aktif" value={data.active_bookings} tint="bg-violet-50 text-violet-600" />
        <StatCard testid="stat-revenue" icon={Wallet} label="Pendapatan Bulan Ini" value={formatRupiah(data.revenue)} tint="bg-blue-50 text-blue-600" />
        <StatCard testid="stat-outstanding" icon={AlertCircle} label="Total Sisa Tagihan" value={formatRupiah(data.outstanding)} tint="bg-red-50 text-red-600" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Chart */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_2px_10px_rgba(0,0,0,0.03)] lg:col-span-2">
          <h2 className="font-heading text-lg font-semibold text-slate-800">Pendapatan 6 Bulan Terakhir</h2>
          <div className="mt-4 h-64 w-full" data-testid="revenue-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.chart} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => (v >= 1000000 ? `${v / 1000000}jt` : v >= 1000 ? `${v / 1000}rb` : v)}
                />
                <Tooltip formatter={(v) => formatRupiah(v)} cursor={{ fill: "#f8fafc" }} />
                <Bar dataKey="pendapatan" fill="#2563eb" radius={[6, 6, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Returning today */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_2px_10px_rgba(0,0,0,0.03)]">
          <div className="mb-4 flex items-center gap-2">
            <Clock className="h-4 w-4 text-red-500" />
            <h2 className="font-heading text-lg font-semibold text-slate-800">Kembali Hari Ini</h2>
          </div>
          <div className="space-y-3" data-testid="returning-today">
            {data.returning_today.length === 0 && (
              <p className="text-sm text-slate-400">Tidak ada kendaraan yang kembali hari ini.</p>
            )}
            {data.returning_today.map((r) => (
              <div key={r.id} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                <div className="text-sm font-semibold text-slate-800">
                  {r.vehicle?.merek} {r.vehicle?.tipe}
                </div>
                <div className="text-xs text-slate-500">{r.customer?.nama}</div>
              </div>
            ))}
          </div>

          <div className="mb-3 mt-6 flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-amber-500" />
            <h2 className="font-heading text-base font-semibold text-slate-800">Kembali Beberapa Hari Lagi</h2>
          </div>
          <div className="space-y-3" data-testid="returning-soon">
            {data.returning_soon.length === 0 && (
              <p className="text-sm text-slate-400">Tidak ada.</p>
            )}
            {data.returning_soon.map((r) => (
              <div key={r.id} className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
                <div>
                  <div className="text-sm font-semibold text-slate-800">
                    {r.vehicle?.merek} {r.vehicle?.tipe}
                  </div>
                  <div className="text-xs text-slate-500">{r.customer?.nama}</div>
                </div>
                <div className="text-xs font-medium text-amber-600">{formatTanggal(r.tanggal_kembali)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent rentals */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_2px_10px_rgba(0,0,0,0.03)]">
        <h2 className="mb-4 font-heading text-lg font-semibold text-slate-800">Rental Terbaru</h2>
        <div className="space-y-2" data-testid="recent-rentals">
          {data.recent.length === 0 && <p className="text-sm text-slate-400">Belum ada rental.</p>}
          {data.recent.map((r) => (
            <div
              key={r.id}
              className="flex flex-col gap-2 rounded-lg border border-slate-100 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-14 shrink-0 overflow-hidden rounded-md bg-slate-100">
                  {r.vehicle?.foto_url && (
                    <img src={mediaUrl(r.vehicle.foto_url)} alt="" className="h-full w-full object-cover" />
                  )}
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-800">
                    {r.vehicle?.merek} {r.vehicle?.tipe}
                  </div>
                  <div className="text-xs text-slate-500">
                    {r.customer?.nama} · {formatTanggal(r.tanggal_mulai)}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-slate-800">{formatRupiah(r.total)}</span>
                <StatusBadge status={r.status_rental} type="rental" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
