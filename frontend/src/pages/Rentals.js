import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  formatRupiah, formatDurasi, formatPeriode, waLink,
  msgKonfirmasi, msgPengingatBayar, msgPengingatKembali, msgInvoice, invoiceUrl,
} from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Plus, Loader2, ClipboardList, MessageCircle, MoreVertical, Trash2, Play,
  CalendarDays, Clock, CircleCheck, CircleDot, Pencil, FileText, Wallet,
} from "lucide-react";

const empty = {
  customer_id: "", vehicle_id: "", tipe_sewa: "Harian",
  tanggal_mulai: "", tanggal_kembali: "",
  waktu_mulai: "", waktu_kembali: "",
  harga_per_hari: "", deposit: "0", catatan: "",
};

const rentalStatuses = ["Booking", "Aktif", "Selesai", "Dibatalkan"];

function splitDT(v) {
  if (!v) return { tanggal: "", waktu: "" };
  const [tanggal, waktu] = v.split("T");
  return { tanggal, waktu: waktu || "" };
}
function joinDT(tanggal, waktu) {
  if (!tanggal) return "";
  return `${tanggal}T${waktu || "00:00"}`;
}

export default function Rentals() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("Semua");
  const [payFilter, setPayFilter] = useState("Semua");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [dtStart, setDtStart] = useState("");
  const [dtEnd, setDtEnd] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [editConfirmOpen, setEditConfirmOpen] = useState(false);
  const [startRental, setStartRental] = useState(null);
  const [cancelRental, setCancelRental] = useState(null);
  const [deleteRental, setDeleteRental] = useState(null);
  const [selesaiWarn, setSelesaiWarn] = useState(null);
  const [payRental, setPayRental] = useState(null);
  const [payForm, setPayForm] = useState({ amount: "", catatan: "" });

  const { data: rentals = [], isLoading } = useQuery({
    queryKey: ["rentals", filter],
    queryFn: async () => (await api.get("/rentals", { params: { status: filter } })).data,
  });
  const { data: vehicles = [] } = useQuery({
    queryKey: ["vehicles-all"],
    queryFn: async () => (await api.get("/vehicles")).data,
  });
  const { data: customers = [] } = useQuery({
    queryKey: ["customers-all"],
    queryFn: async () => (await api.get("/customers")).data,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["rentals"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["vehicles"] });
    qc.invalidateQueries({ queryKey: ["vehicles-all"] });
    qc.invalidateQueries({ queryKey: ["customers"] });
  };

  const selectedVehicle = vehicles.find((v) => v.id === form.vehicle_id);
  const effHarga = form.harga_per_hari !== "" ? Number(form.harga_per_hari) : (selectedVehicle?.harga_per_hari || 0);

  const commonPayload = () => {
    if (form.tipe_sewa === "24 Jam") {
      const s = splitDT(dtStart);
      const e = splitDT(dtEnd);
      return {
        customer_id: form.customer_id, vehicle_id: form.vehicle_id, tipe_sewa: "24 Jam",
        tanggal_mulai: s.tanggal, waktu_mulai: s.waktu,
        tanggal_kembali: e.tanggal, waktu_kembali: e.waktu,
        catatan: form.catatan,
      };
    }
    return {
      customer_id: form.customer_id, vehicle_id: form.vehicle_id, tipe_sewa: "Harian",
      tanggal_mulai: form.tanggal_mulai, tanggal_kembali: form.tanggal_kembali,
      waktu_mulai: null, waktu_kembali: null, catatan: form.catatan,
    };
  };

  const calc = useMemo(() => {
    if (!selectedVehicle) return null;
    const price = effHarga;
    if (form.tipe_sewa === "24 Jam") {
      if (!dtStart || !dtEnd) return null;
      const hours = (new Date(dtEnd) - new Date(dtStart)) / 3600000;
      if (hours <= 0) return { invalid: true };
      const units = Math.max(Math.ceil(hours / 24), 1);
      return { units, hours: Math.round(hours * 10) / 10, subtotal: units * price, total: units * price, harga: price, tipe: "24 Jam" };
    }
    if (!form.tanggal_mulai || !form.tanggal_kembali) return null;
    const days = Math.round((new Date(form.tanggal_kembali) - new Date(form.tanggal_mulai)) / 86400000) + 1;
    if (days <= 0) return { invalid: true };
    return { units: days, subtotal: days * price, total: days * price, harga: price, tipe: "Harian" };
  }, [selectedVehicle, effHarga, form.tipe_sewa, form.tanggal_mulai, form.tanggal_kembali, dtStart, dtEnd]);

  const createMut = useMutation({
    mutationFn: async (status_rental) =>
      (await api.post("/rentals", { ...commonPayload(), deposit: Number(form.deposit || 0), status_rental })).data,
    onSuccess: (_data, status_rental) => {
      toast.success(status_rental === "Aktif"
        ? "✓ Rental berhasil dibuat dan sekarang aktif."
        : "✓ Rental berhasil disimpan sebagai Booking.");
      setConfirmOpen(false); setDialogOpen(false); invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const editMut = useMutation({
    mutationFn: async () =>
      (await api.put(`/rentals/${editing.id}`, { ...commonPayload(), harga_per_hari: Number(form.harga_per_hari || 0) })).data,
    onSuccess: () => {
      toast.success("✓ Perubahan rental berhasil disimpan.");
      setEditConfirmOpen(false); setDialogOpen(false); setEditing(null); invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const statusMut = useMutation({
    mutationFn: async ({ id, body }) => (await api.patch(`/rentals/${id}/status`, body)).data,
    onSuccess: () => { toast.success("Status diperbarui"); invalidate(); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const startMut = useMutation({
    mutationFn: async (id) => (await api.patch(`/rentals/${id}/status`, { status_rental: "Aktif" })).data,
    onSuccess: () => { toast.success("✓ Rental sekarang aktif. Kendaraan berstatus Disewa."); setStartRental(null); invalidate(); },
    onError: (e) => { toast.error(formatApiErrorDetail(e.response?.data?.detail)); setStartRental(null); },
  });

  const cancelMut = useMutation({
    mutationFn: async (id) => (await api.patch(`/rentals/${id}/status`, { status_rental: "Dibatalkan" })).data,
    onSuccess: () => { toast.success("Booking dibatalkan. Kendaraan kembali tersedia."); setCancelRental(null); invalidate(); },
    onError: (e) => { toast.error(formatApiErrorDetail(e.response?.data?.detail)); setCancelRental(null); },
  });

  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/rentals/${id}`)).data,
    onSuccess: () => { toast.success("Rental dihapus"); setDeleteRental(null); invalidate(); },
    onError: (e) => { toast.error(formatApiErrorDetail(e.response?.data?.detail)); setDeleteRental(null); },
  });

  const payMut = useMutation({
    mutationFn: async () => (await api.post(`/rentals/${payRental.id}/payments`, { amount: Number(payForm.amount), catatan: payForm.catatan })).data,
    onSuccess: (d) => {
      toast.success(d.status_pembayaran === "Lunas" ? "✓ Pembayaran lunas!" : "Pembayaran dicatat");
      setPayRental(null); setPayForm({ amount: "", catatan: "" }); invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const openAdd = () => { setEditing(null); setForm(empty); setDtStart(""); setDtEnd(""); setDialogOpen(true); };
  const doOpenEdit = (r) => {
    setEditing(r);
    setForm({
      customer_id: r.customer_id, vehicle_id: r.vehicle_id, tipe_sewa: r.tipe_sewa || "Harian",
      tanggal_mulai: r.tanggal_mulai, tanggal_kembali: r.tanggal_kembali,
      waktu_mulai: r.waktu_mulai || "", waktu_kembali: r.waktu_kembali || "",
      harga_per_hari: String(r.harga_per_hari || ""), deposit: "0", catatan: r.catatan || "",
    });
    if (r.tipe_sewa === "24 Jam") {
      setDtStart(joinDT(r.tanggal_mulai, r.waktu_mulai));
      setDtEnd(joinDT(r.tanggal_kembali, r.waktu_kembali));
    } else { setDtStart(""); setDtEnd(""); }
    setDialogOpen(true);
  };
  const openEdit = (r) => {
    if (r.status_rental === "Selesai") { setSelesaiWarn(r); return; }
    doOpenEdit(r);
  };

  const onVehicleChange = (v) => {
    const veh = vehicles.find((x) => x.id === v);
    setForm((f) => ({ ...f, vehicle_id: v, harga_per_hari: veh ? String(veh.harga_per_hari) : f.harga_per_hari }));
  };

  const formValid = form.customer_id && form.vehicle_id && calc && !calc.invalid;
  const paySisa = payRental ? payRental.sisa : 0;

  const displayed = useMemo(() => rentals.filter((r) => {
    if (payFilter === "Belum Lunas") return r.sisa > 0;
    if (payFilter === "DP") return r.total_paid > 0 && r.sisa > 0;
    if (payFilter === "Lunas") return r.sisa <= 0;
    return true;
  }), [rentals, payFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Rental / Booking</h1>
          <p className="mt-1 text-sm text-slate-500">Kelola transaksi penyewaan kendaraan.</p>
        </div>
        <Button data-testid="add-rental-button" onClick={openAdd} className="gap-2 bg-blue-600 hover:bg-blue-700">
          <Plus className="h-4 w-4" /> Buat Rental
        </Button>
      </div>

      <div className="space-y-2">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {["Semua", ...rentalStatuses].map((s) => (
            <button
              key={s}
              data-testid={`rental-filter-${s}`}
              onClick={() => setFilter(s)}
              className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200 ${
                filter === s ? "bg-blue-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="whitespace-nowrap text-xs font-medium text-slate-400">Pembayaran:</span>
          {["Semua", "Belum Lunas", "DP", "Lunas"].map((s) => (
            <button
              key={s}
              data-testid={`pay-filter-${s}`}
              onClick={() => setPayFilter(s)}
              className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition-colors duration-200 ${
                payFilter === s
                  ? "bg-slate-800 text-white"
                  : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
      ) : displayed.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center">
          <ClipboardList className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">Tidak ada rental untuk filter ini.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="rental-list">
          {displayed.map((r) => (
            <div
              key={r.id}
              data-testid={`rental-card-${r.id}`}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_2px_10px_rgba(0,0,0,0.03)] sm:p-5"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-500">{r.transaksi_id}</span>
                    <StatusBadge status={r.status_rental} type="rental" testid={`rental-status-${r.id}`} />
                    <StatusBadge status={r.status_pembayaran} type="pay" testid={`rental-pay-${r.id}`} />
                    <span
                      data-testid={`rental-tipe-${r.id}`}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                        r.tipe_sewa === "24 Jam" ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-teal-200 bg-teal-50 text-teal-700"
                      }`}
                    >
                      {r.tipe_sewa === "24 Jam" ? <Clock className="h-3 w-3" /> : <CalendarDays className="h-3 w-3" />}
                      {r.tipe_sewa || "Harian"}
                    </span>
                  </div>
                  <h3 className="mt-2 font-heading font-semibold text-slate-900">
                    {r.vehicle?.merek} {r.vehicle?.tipe}
                    <span className="ml-2 text-sm font-normal text-slate-400">{r.vehicle?.nomor_polisi}</span>
                  </h3>
                  <p className="text-sm text-slate-600">{r.customer?.nama}</p>
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                    <span data-testid={`rental-periode-${r.id}`}>{formatPeriode(r)}</span>
                    <span className="font-medium text-slate-600" data-testid={`rental-durasi-${r.id}`}>{formatDurasi(r)} × {formatRupiah(r.harga_per_hari)}</span>
                  </div>
                  {/* Payment summary */}
                  <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <span className="text-slate-500">Total: <span className="font-semibold text-slate-800">{formatRupiah(r.total)}</span></span>
                    <span className="text-slate-500">Sudah Dibayar: <span className="font-semibold text-emerald-600" data-testid={`rental-paid-${r.id}`}>{formatRupiah(r.total_paid)}</span></span>
                    <span className="text-slate-500">Sisa Pembayaran: <span className={`font-bold ${r.sisa > 0 ? "text-red-600" : "text-emerald-600"}`} data-testid={`rental-sisa-${r.id}`}>{formatRupiah(r.sisa)}</span></span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {r.status_rental === "Booking" && (
                    <>
                      <Button size="sm" data-testid={`rental-start-${r.id}`} className="gap-1.5 bg-emerald-600 hover:bg-emerald-700" onClick={() => setStartRental(r)}>
                        <Play className="h-4 w-4" /> Mulai Rental
                      </Button>
                      <Button variant="outline" size="sm" data-testid={`rental-cancel-${r.id}`} className="text-slate-600" onClick={() => setCancelRental(r)}>
                        Batalkan
                      </Button>
                    </>
                  )}
                  {r.sisa > 0 && r.status_rental !== "Dibatalkan" && (
                    <Button size="sm" data-testid={`rental-pay-btn-${r.id}`} className="gap-1.5 bg-blue-600 hover:bg-blue-700" onClick={() => { setPayRental(r); setPayForm({ amount: "", catatan: "" }); }}>
                      <Wallet className="h-4 w-4" /> Bayar
                    </Button>
                  )}
                  <Button variant="outline" size="sm" data-testid={`rental-edit-${r.id}`} className="gap-1.5" onClick={() => openEdit(r)}>
                    <Pencil className="h-4 w-4" /> Edit
                  </Button>
                  <a href={invoiceUrl(r.id)} target="_blank" rel="noreferrer">
                    <Button variant="outline" size="sm" data-testid={`rental-invoice-${r.id}`} className="gap-1.5">
                      <FileText className="h-4 w-4" /> Invoice
                    </Button>
                  </a>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" data-testid={`rental-wa-${r.id}`} className="gap-1.5 border-green-200 text-green-700 hover:bg-green-50">
                        <MessageCircle className="h-4 w-4" /> WhatsApp
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuLabel>Kirim Pesan</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem asChild>
                        <a data-testid={`wa-invoice-${r.id}`} href={waLink(r.customer?.whatsapp, msgInvoice(r))} target="_blank" rel="noreferrer">Kirim Invoice</a>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <a data-testid={`wa-konfirmasi-${r.id}`} href={waLink(r.customer?.whatsapp, msgKonfirmasi(r))} target="_blank" rel="noreferrer">Konfirmasi Booking</a>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <a data-testid={`wa-bayar-${r.id}`} href={waLink(r.customer?.whatsapp, msgPengingatBayar(r))} target="_blank" rel="noreferrer">Pengingat Pembayaran</a>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <a data-testid={`wa-kembali-${r.id}`} href={waLink(r.customer?.whatsapp, msgPengingatKembali(r))} target="_blank" rel="noreferrer">Pengingat Pengembalian</a>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="icon" className="h-9 w-9" data-testid={`rental-menu-${r.id}`}>
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                      <DropdownMenuLabel>Status Rental</DropdownMenuLabel>
                      {rentalStatuses.map((s) => (
                        <DropdownMenuItem key={s} data-testid={`set-rental-${s}-${r.id}`} onClick={() => statusMut.mutate({ id: r.id, body: { status_rental: s } })}>
                          {s} {r.status_rental === s && "✓"}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem className="text-red-600" data-testid={`rental-delete-${r.id}`} onClick={() => setDeleteRental(r)}>
                        <Trash2 className="mr-2 h-4 w-4" /> Hapus Rental
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit rental form */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">{editing ? "Edit Rental" : "Buat Rental Baru"}</DialogTitle>
            {editing && <DialogDescription>No. Transaksi {editing.transaksi_id} tidak akan berubah.</DialogDescription>}
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Pelanggan</Label>
              <Select value={form.customer_id} onValueChange={(v) => setForm({ ...form, customer_id: v })}>
                <SelectTrigger data-testid="rental-customer-select" className="mt-1"><SelectValue placeholder="Pilih pelanggan" /></SelectTrigger>
                <SelectContent>
                  {customers.map((c) => <SelectItem key={c.id} value={c.id}>{c.nama} — {c.whatsapp}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Kendaraan</Label>
              <Select value={form.vehicle_id} onValueChange={onVehicleChange}>
                <SelectTrigger data-testid="rental-vehicle-select" className="mt-1"><SelectValue placeholder="Pilih kendaraan" /></SelectTrigger>
                <SelectContent>
                  {vehicles.map((v) => (
                    <SelectItem key={v.id} value={v.id}>{v.merek} {v.tipe} ({v.nomor_polisi}) — {formatRupiah(v.harga_per_hari)}/hari</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Tipe Sewa</Label>
              <div className="mt-1.5 grid grid-cols-2 gap-3">
                <button type="button" data-testid="rental-tipe-harian" onClick={() => setForm({ ...form, tipe_sewa: "Harian" })}
                  className={`flex items-center justify-center gap-2 rounded-xl border-2 py-3 text-sm font-semibold transition-colors duration-200 ${form.tipe_sewa === "Harian" ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}>
                  <CalendarDays className="h-4 w-4" /> 📅 Harian
                </button>
                <button type="button" data-testid="rental-tipe-24jam" onClick={() => setForm({ ...form, tipe_sewa: "24 Jam" })}
                  className={`flex items-center justify-center gap-2 rounded-xl border-2 py-3 text-sm font-semibold transition-colors duration-200 ${form.tipe_sewa === "24 Jam" ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"}`}>
                  <Clock className="h-4 w-4" /> ⏱️ 24 Jam
                </button>
              </div>
            </div>

            {form.tipe_sewa === "Harian" ? (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tanggal Mulai</Label>
                  <Input type="date" data-testid="rental-start-input" value={form.tanggal_mulai} onChange={(e) => setForm({ ...form, tanggal_mulai: e.target.value })} className="mt-1" />
                </div>
                <div>
                  <Label>Tanggal Kembali</Label>
                  <Input type="date" data-testid="rental-end-input" value={form.tanggal_kembali} onChange={(e) => setForm({ ...form, tanggal_kembali: e.target.value })} className="mt-1" />
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                <div>
                  <Label>Tanggal & Waktu Mulai</Label>
                  <Input type="datetime-local" data-testid="rental-start-dt-input" value={dtStart} onChange={(e) => setDtStart(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <Label>Tanggal & Waktu Berakhir</Label>
                  <Input type="datetime-local" data-testid="rental-end-dt-input" value={dtEnd} onChange={(e) => setDtEnd(e.target.value)} className="mt-1" />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tarif per Hari</Label>
                <Input type="number" data-testid="rental-harga-input" value={form.harga_per_hari}
                  onChange={(e) => setForm({ ...form, harga_per_hari: e.target.value })} className="mt-1"
                  placeholder={selectedVehicle ? String(selectedVehicle.harga_per_hari) : ""} />
              </div>
              {!editing && (
                <div>
                  <Label>DP / Deposit Awal</Label>
                  <Input type="number" data-testid="rental-deposit-input" value={form.deposit} onChange={(e) => setForm({ ...form, deposit: e.target.value })} className="mt-1" />
                </div>
              )}
            </div>
            <div>
              <Label>Catatan</Label>
              <Textarea data-testid="rental-catatan-input" value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} className="mt-1" />
            </div>

            <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4" data-testid="rental-calc">
              {calc?.invalid ? (
                <p className="text-sm text-red-600">{form.tipe_sewa === "24 Jam" ? "Waktu berakhir harus setelah waktu mulai." : "Tanggal kembali tidak boleh sebelum tanggal mulai."}</p>
              ) : calc ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-slate-500">Durasi</span>
                    <span className="font-medium">{calc.tipe === "24 Jam" ? `${calc.units} × 24 Jam (${calc.hours} jam)` : `${calc.units} hari`}</span>
                  </div>
                  <div className="flex justify-between"><span className="text-slate-500">Tarif per hari</span><span className="font-medium">{formatRupiah(calc.harga)}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span className="font-medium">{formatRupiah(calc.subtotal)}</span></div>
                  <div className="mt-2 flex justify-between border-t border-blue-100 pt-2 text-base"><span className="font-semibold text-slate-700">Total</span><span className="font-bold text-blue-600" data-testid="rental-calc-total">{formatRupiah(calc.total)}</span></div>
                </div>
              ) : (
                <p className="text-sm text-slate-400">Pilih kendaraan & {form.tipe_sewa === "24 Jam" ? "waktu" : "tanggal"} untuk melihat perhitungan otomatis.</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Batal</Button>
            {editing ? (
              <Button data-testid="rental-save-edit-button" className="bg-blue-600 hover:bg-blue-700" disabled={!formValid} onClick={() => setEditConfirmOpen(true)}>
                Simpan Perubahan
              </Button>
            ) : (
              <Button data-testid="rental-save-button" className="bg-blue-600 hover:bg-blue-700" disabled={!formValid} onClick={() => setConfirmOpen(true)}>
                Buat Rental
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Post-creation confirmation */}
      <Dialog open={confirmOpen} onOpenChange={(o) => !createMut.isPending && setConfirmOpen(o)}>
        <DialogContent className="sm:max-w-md" data-testid="rental-confirm-modal">
          <DialogHeader>
            <DialogTitle className="font-heading">Order berhasil dibuat</DialogTitle>
            <DialogDescription>Apa yang ingin Anda lakukan dengan rental ini?</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 py-2">
            <button data-testid="confirm-aktif-button" disabled={createMut.isPending} onClick={() => createMut.mutate("Aktif")}
              className="flex items-center gap-3 rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4 text-left transition-colors duration-200 hover:border-emerald-400 disabled:opacity-60">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-600 text-white">
                {createMut.isPending && createMut.variables === "Aktif" ? <Loader2 className="h-5 w-5 animate-spin" /> : <CircleCheck className="h-6 w-6" />}
              </div>
              <div>
                <div className="font-heading font-semibold text-emerald-800">🟢 Aktif Sekarang</div>
                <div className="text-xs text-emerald-700">Rental langsung aktif, kendaraan menjadi Disewa</div>
              </div>
            </button>
            <button data-testid="confirm-booking-button" disabled={createMut.isPending} onClick={() => createMut.mutate("Booking")}
              className="flex items-center gap-3 rounded-xl border-2 border-blue-200 bg-blue-50 p-4 text-left transition-colors duration-200 hover:border-blue-400 disabled:opacity-60">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-blue-600 text-white">
                {createMut.isPending && createMut.variables === "Booking" ? <Loader2 className="h-5 w-5 animate-spin" /> : <CircleDot className="h-6 w-6" />}
              </div>
              <div>
                <div className="font-heading font-semibold text-blue-800">🔵 Simpan sebagai Booking</div>
                <div className="text-xs text-blue-700">Kendaraan tetap tersedia, tanggal tetap terkunci</div>
              </div>
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit confirmation summary */}
      <AlertDialog open={editConfirmOpen} onOpenChange={(o) => !editMut.isPending && setEditConfirmOpen(o)}>
        <AlertDialogContent data-testid="rental-edit-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Simpan perubahan rental?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-1 text-sm text-slate-600">
                <div>Pelanggan: <b>{customers.find((c) => c.id === form.customer_id)?.nama}</b></div>
                <div>Kendaraan: <b>{vehicles.find((v) => v.id === form.vehicle_id)?.merek} {vehicles.find((v) => v.id === form.vehicle_id)?.tipe}</b></div>
                <div>Tipe: <b>{form.tipe_sewa}</b> · Durasi: <b>{calc ? (calc.tipe === "24 Jam" ? `${calc.units} × 24 Jam` : `${calc.units} hari`) : "-"}</b></div>
                <div>Total baru: <b>{calc ? formatRupiah(calc.total) : "-"}</b></div>
                <div className="text-xs text-slate-400">No. transaksi & riwayat pembayaran tetap dipertahankan.</div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-edit-button" className="bg-blue-600 hover:bg-blue-700" onClick={(e) => { e.preventDefault(); editMut.mutate(); }}>
              {editMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Simpan"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Payment dialog */}
      <Dialog open={!!payRental} onOpenChange={() => setPayRental(null)}>
        <DialogContent className="sm:max-w-md" data-testid="payment-modal">
          <DialogHeader>
            <DialogTitle className="font-heading">Tambah Pembayaran</DialogTitle>
            <DialogDescription>{payRental?.transaksi_id} — {payRental?.customer?.nama}</DialogDescription>
          </DialogHeader>
          {payRental && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-2 rounded-lg bg-slate-50 p-3 text-sm">
                <div><div className="text-xs text-slate-400">Total</div><div className="font-semibold">{formatRupiah(payRental.total)}</div></div>
                <div><div className="text-xs text-slate-400">Sudah Dibayar</div><div className="font-semibold text-emerald-600">{formatRupiah(payRental.total_paid)}</div></div>
                <div><div className="text-xs text-slate-400">Sisa</div><div className="font-bold text-red-600">{formatRupiah(payRental.sisa)}</div></div>
              </div>
              <div>
                <Label>Jumlah Pembayaran</Label>
                <Input type="number" data-testid="payment-amount-input" value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} className="mt-1" placeholder={`Maks ${paySisa}`} />
                <button type="button" data-testid="payment-full-button" className="mt-1 text-xs font-medium text-blue-600 hover:underline" onClick={() => setPayForm({ ...payForm, amount: String(paySisa) })}>
                  Bayar penuh ({formatRupiah(paySisa)})
                </button>
              </div>
              <div>
                <Label>Catatan (opsional)</Label>
                <Input data-testid="payment-note-input" value={payForm.catatan} onChange={(e) => setPayForm({ ...payForm, catatan: e.target.value })} className="mt-1" placeholder="mis. Pelunasan / Tambahan" />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPayRental(null)}>Batal</Button>
            <Button data-testid="payment-save-button" className="bg-blue-600 hover:bg-blue-700"
              disabled={payMut.isPending || !payForm.amount || Number(payForm.amount) <= 0 || Number(payForm.amount) > paySisa}
              onClick={() => payMut.mutate()}>
              {payMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Catat Pembayaran"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mulai Rental confirm */}
      <AlertDialog open={!!startRental} onOpenChange={() => setStartRental(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mulai rental ini sekarang?</AlertDialogTitle>
            <AlertDialogDescription>Status berubah menjadi Aktif dan kendaraan menjadi Disewa. Data pelanggan, tanggal, harga, dan pembayaran tetap dipertahankan.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-mulai-button" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => startMut.mutate(startRental.id)}>Mulai Rental</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Cancel confirm */}
      <AlertDialog open={!!cancelRental} onOpenChange={() => setCancelRental(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Batalkan booking ini?</AlertDialogTitle>
            <AlertDialogDescription>Booking akan dibatalkan dan tidak lagi mengunci ketersediaan kendaraan.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Kembali</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-cancel-button" className="bg-red-600 hover:bg-red-700" onClick={() => cancelMut.mutate(cancelRental.id)}>Batalkan Booking</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Selesai edit warning */}
      <AlertDialog open={!!selesaiWarn} onOpenChange={() => setSelesaiWarn(null)}>
        <AlertDialogContent data-testid="selesai-warn-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>⚠️ Transaksi ini sudah selesai</AlertDialogTitle>
            <AlertDialogDescription>
              Perubahan dapat memengaruhi data pembayaran, laporan keuangan, dan riwayat kendaraan.
              Apakah Anda yakin ingin mengedit transaksi ini?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="selesai-warn-cancel">Batal</AlertDialogCancel>
            <AlertDialogAction
              data-testid="selesai-warn-continue"
              className="bg-amber-600 hover:bg-amber-700"
              onClick={() => { const r = selesaiWarn; setSelesaiWarn(null); doOpenEdit(r); }}
            >
              Lanjutkan Edit
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteRental} onOpenChange={() => setDeleteRental(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus rental?</AlertDialogTitle>
            <AlertDialogDescription>Tindakan ini tidak dapat dibatalkan.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete-button" className="bg-red-600 hover:bg-red-700" onClick={() => deleteMut.mutate(deleteRental.id)}>Hapus</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
