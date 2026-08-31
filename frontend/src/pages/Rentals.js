import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  formatRupiah, formatTanggal, waLink,
  msgKonfirmasi, msgPengingatBayar, msgPengingatKembali,
} from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { Plus, Loader2, ClipboardList, MessageCircle, MoreVertical, Trash2 } from "lucide-react";

const empty = {
  customer_id: "", vehicle_id: "", tanggal_mulai: "", tanggal_kembali: "",
  deposit: "0", status_pembayaran: "Belum bayar", status_rental: "Booking", catatan: "",
};

const rentalStatuses = ["Booking", "Aktif", "Selesai", "Dibatalkan"];
const payStatuses = ["Belum bayar", "DP", "Lunas"];

export default function Rentals() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("Semua");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState(empty);

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
  };

  const selectedVehicle = vehicles.find((v) => v.id === form.vehicle_id);
  const calc = useMemo(() => {
    if (!selectedVehicle || !form.tanggal_mulai || !form.tanggal_kembali) return null;
    const d1 = new Date(form.tanggal_mulai);
    const d2 = new Date(form.tanggal_kembali);
    const days = Math.round((d2 - d1) / 86400000);
    if (days <= 0) return { invalid: true };
    const subtotal = days * selectedVehicle.harga_per_hari;
    return { days, subtotal, total: subtotal, harga: selectedVehicle.harga_per_hari };
  }, [selectedVehicle, form.tanggal_mulai, form.tanggal_kembali]);

  const createMut = useMutation({
    mutationFn: async (payload) =>
      (await api.post("/rentals", { ...payload, deposit: Number(payload.deposit || 0) })).data,
    onSuccess: () => {
      toast.success("Rental berhasil dibuat");
      setDialogOpen(false);
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const statusMut = useMutation({
    mutationFn: async ({ id, body }) => (await api.patch(`/rentals/${id}/status`, body)).data,
    onSuccess: () => {
      toast.success("Status diperbarui");
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/rentals/${id}`)).data,
    onSuccess: () => { toast.success("Rental dihapus"); invalidate(); },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const openAdd = () => { setForm(empty); setDialogOpen(true); };

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

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
      ) : rentals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center">
          <ClipboardList className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">Belum ada rental.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="rental-list">
          {rentals.map((r) => (
            <div
              key={r.id}
              data-testid={`rental-card-${r.id}`}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_2px_10px_rgba(0,0,0,0.03)] sm:p-5"
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-500">{r.transaksi_id}</span>
                    <StatusBadge status={r.status_rental} type="rental" testid={`rental-status-${r.id}`} />
                    <StatusBadge status={r.status_pembayaran} type="pay" testid={`rental-pay-${r.id}`} />
                  </div>
                  <h3 className="mt-2 font-heading font-semibold text-slate-900">
                    {r.vehicle?.merek} {r.vehicle?.tipe}
                    <span className="ml-2 text-sm font-normal text-slate-400">{r.vehicle?.nomor_polisi}</span>
                  </h3>
                  <p className="text-sm text-slate-600">{r.customer?.nama}</p>
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                    <span>{formatTanggal(r.tanggal_mulai)} → {formatTanggal(r.tanggal_kembali)}</span>
                    <span>{r.jumlah_hari} hari × {formatRupiah(r.harga_per_hari)}</span>
                    <span className="font-semibold text-blue-600">Total: {formatRupiah(r.total)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
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
                        <DropdownMenuItem
                          key={s}
                          data-testid={`set-rental-${s}-${r.id}`}
                          onClick={() => statusMut.mutate({ id: r.id, body: { status_rental: s } })}
                        >
                          {s} {r.status_rental === s && "✓"}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel>Status Pembayaran</DropdownMenuLabel>
                      {payStatuses.map((s) => (
                        <DropdownMenuItem
                          key={s}
                          data-testid={`set-pay-${s}-${r.id}`}
                          onClick={() => statusMut.mutate({ id: r.id, body: { status_pembayaran: s } })}
                        >
                          {s} {r.status_pembayaran === s && "✓"}
                        </DropdownMenuItem>
                      ))}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-red-600"
                        data-testid={`rental-delete-${r.id}`}
                        onClick={() => deleteMut.mutate(r.id)}
                      >
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

      {/* Create rental */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Buat Rental Baru</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Pelanggan</Label>
              <Select value={form.customer_id} onValueChange={(v) => setForm({ ...form, customer_id: v })}>
                <SelectTrigger data-testid="rental-customer-select" className="mt-1">
                  <SelectValue placeholder="Pilih pelanggan" />
                </SelectTrigger>
                <SelectContent>
                  {customers.map((c) => <SelectItem key={c.id} value={c.id}>{c.nama} — {c.whatsapp}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Kendaraan</Label>
              <Select value={form.vehicle_id} onValueChange={(v) => setForm({ ...form, vehicle_id: v })}>
                <SelectTrigger data-testid="rental-vehicle-select" className="mt-1">
                  <SelectValue placeholder="Pilih kendaraan" />
                </SelectTrigger>
                <SelectContent>
                  {vehicles.map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.merek} {v.tipe} ({v.nomor_polisi}) — {formatRupiah(v.harga_per_hari)}/hari
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Deposit</Label>
                <Input type="number" data-testid="rental-deposit-input" value={form.deposit} onChange={(e) => setForm({ ...form, deposit: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Status Pembayaran</Label>
                <Select value={form.status_pembayaran} onValueChange={(v) => setForm({ ...form, status_pembayaran: v })}>
                  <SelectTrigger data-testid="rental-pay-select" className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {payStatuses.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Status Rental</Label>
              <Select value={form.status_rental} onValueChange={(v) => setForm({ ...form, status_rental: v })}>
                <SelectTrigger data-testid="rental-status-select" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {rentalStatuses.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Catatan</Label>
              <Textarea data-testid="rental-catatan-input" value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} className="mt-1" />
            </div>

            {/* Auto calculation */}
            <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4" data-testid="rental-calc">
              {calc?.invalid ? (
                <p className="text-sm text-red-600">Tanggal kembali harus setelah tanggal mulai.</p>
              ) : calc ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between"><span className="text-slate-500">Durasi</span><span className="font-medium">{calc.days} hari</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Harga per hari</span><span className="font-medium">{formatRupiah(calc.harga)}</span></div>
                  <div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span className="font-medium">{formatRupiah(calc.subtotal)}</span></div>
                  <div className="mt-2 flex justify-between border-t border-blue-100 pt-2 text-base"><span className="font-semibold text-slate-700">Total</span><span className="font-bold text-blue-600" data-testid="rental-calc-total">{formatRupiah(calc.total)}</span></div>
                </div>
              ) : (
                <p className="text-sm text-slate-400">Pilih kendaraan & tanggal untuk melihat perhitungan otomatis.</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Batal</Button>
            <Button
              data-testid="rental-save-button"
              className="bg-blue-600 hover:bg-blue-700"
              disabled={createMut.isPending || !form.customer_id || !form.vehicle_id || !calc || calc.invalid}
              onClick={() => createMut.mutate(form)}
            >
              {createMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Simpan Rental"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
