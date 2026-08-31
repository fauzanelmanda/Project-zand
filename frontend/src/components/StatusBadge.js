import React from "react";

const vehicleStyles = {
  Tersedia: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Disewa: "bg-blue-50 text-blue-700 border-blue-200",
  Maintenance: "bg-amber-50 text-amber-700 border-amber-200",
};

const rentalStyles = {
  Booking: "bg-violet-50 text-violet-700 border-violet-200",
  Aktif: "bg-blue-50 text-blue-700 border-blue-200",
  Selesai: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Dibatalkan: "bg-slate-100 text-slate-500 border-slate-200",
};

const payStyles = {
  "Belum bayar": "bg-red-50 text-red-700 border-red-200",
  DP: "bg-amber-50 text-amber-700 border-amber-200",
  Lunas: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

export function StatusBadge({ status, type = "vehicle", testid }) {
  const map = type === "rental" ? rentalStyles : type === "pay" ? payStyles : vehicleStyles;
  const cls = map[status] || "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span
      data-testid={testid}
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {status}
    </span>
  );
}
