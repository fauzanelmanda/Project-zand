import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import { formatRupiah } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ClipboardList, Wallet, KeyRound, CheckCircle2, XCircle } from "lucide-react";

const presets = [
  { key: "today", label: "Hari Ini" },
  { key: "week", label: "Minggu Ini" },
  { key: "month", label: "Bulan Ini" },
  { key: "custom", label: "Kustom" },
];

function rangeFor(key) {
  const today = new Date();
  const fmt = (d) => d.toISOString().slice(0, 10);
  if (key === "today") return { start: fmt(today), end: fmt(today) };
  if (key === "week") {
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(today.setDate(diff));
    const sunday = new Date(monday); sunday.setDate(monday.getDate() + 6);
    return { start: fmt(monday), end: fmt(sunday) };
  }
  if (key === "month") {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return { start: fmt(first), end: fmt(last) };
  }
  return { start: "", end: "" };
}

const MetricCard = ({ icon: Icon, label, value, tint, testid }) => (
  <div data-testid={testid} className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_2px_10px_rgba(0,0,0,0.03)]">
    <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-lg ${tint}`}>
      <Icon className="h-5 w-5" />
    </div>
    <div className="text-2xl font-bold tracking-tight text-slate-900">{value}</div>
    <div className="mt-0.5 text-sm text-slate-500">{label}</div>
  </div>
);

export default function Reports() {
  const [preset, setPreset] = useState("month");
  const [custom, setCustom] = useState({ start: "", end: "" });

  const range = preset === "custom" ? custom : rangeFor(preset);
  const enabled = !(preset === "custom" && (!custom.start || !custom.end));

  const { data, isLoading } = useQuery({
    queryKey: ["reports", range.start, range.end],
    queryFn: async () => (await api.get("/reports", { params: { start: range.start, end: range.end } })).data,
    enabled,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Laporan</h1>
        <p className="mt-1 text-sm text-slate-500">Ringkasan performa rental berdasarkan periode.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p.key}
            data-testid={`report-preset-${p.key}`}
            onClick={() => setPreset(p.key)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200 ${
              preset === p.key ? "bg-blue-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {preset === "custom" && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div>
            <Label>Dari Tanggal</Label>
            <Input type="date" data-testid="report-start-input" value={custom.start} onChange={(e) => setCustom({ ...custom, start: e.target.value })} className="mt-1" />
          </div>
          <div>
            <Label>Sampai Tanggal</Label>
            <Input type="date" data-testid="report-end-input" value={custom.end} onChange={(e) => setCustom({ ...custom, end: e.target.value })} className="mt-1" />
          </div>
        </div>
      )}

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <MetricCard testid="report-total-rental" icon={ClipboardList} label="Total Rental" value={data.total_rental} tint="bg-slate-100 text-slate-700" />
          <MetricCard testid="report-total-revenue" icon={Wallet} label="Total Pendapatan" value={formatRupiah(data.total_revenue)} tint="bg-blue-50 text-blue-600" />
          <MetricCard testid="report-aktif" icon={KeyRound} label="Rental Aktif" value={data.aktif} tint="bg-blue-50 text-blue-600" />
          <MetricCard testid="report-selesai" icon={CheckCircle2} label="Rental Selesai" value={data.selesai} tint="bg-emerald-50 text-emerald-600" />
          <MetricCard testid="report-dibatalkan" icon={XCircle} label="Rental Dibatalkan" value={data.dibatalkan} tint="bg-red-50 text-red-600" />
        </div>
      )}
    </div>
  );
}
