import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { formatTanggal, formatRupiah, formatDurasi, formatPeriode, waLink, msgKontak } from "@/lib/format";
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
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Plus, Search, Pencil, Trash2, Loader2, Users, MessageCircle, MapPin, CreditCard } from "lucide-react";

const empty = { nama: "", whatsapp: "", alamat: "", nomor_identitas: "", catatan: "" };

export default function Customers() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [deleteId, setDeleteId] = useState(null);
  const [detail, setDetail] = useState(null);

  const { data: customers = [], isLoading } = useQuery({
    queryKey: ["customers", search],
    queryFn: async () => (await api.get("/customers", { params: { search: search || undefined } })).data,
  });

  const { data: history = [] } = useQuery({
    queryKey: ["customer-rentals", detail?.id],
    queryFn: async () => (await api.get(`/customers/${detail.id}/rentals`)).data,
    enabled: !!detail,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["customers"] });

  const saveMut = useMutation({
    mutationFn: async (payload) => {
      if (editing) return (await api.put(`/customers/${editing.id}`, payload)).data;
      return (await api.post("/customers", payload)).data;
    },
    onSuccess: () => {
      toast.success(editing ? "Pelanggan diperbarui" : "Pelanggan berhasil ditambahkan");
      setDialogOpen(false);
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/customers/${id}`)).data,
    onSuccess: () => {
      toast.success("Pelanggan dihapus");
      setDeleteId(null);
      invalidate();
    },
    onError: (e) => {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setDeleteId(null);
    },
  });

  const openAdd = () => { setEditing(null); setForm(empty); setDialogOpen(true); };
  const openEdit = (c) => { setEditing(c); setForm({ ...c }); setDialogOpen(true); };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Pelanggan</h1>
          <p className="mt-1 text-sm text-slate-500">Kelola data pelanggan rental.</p>
        </div>
        <Button data-testid="add-customer-button" onClick={openAdd} className="gap-2 bg-blue-600 hover:bg-blue-700">
          <Plus className="h-4 w-4" /> Tambah Pelanggan
        </Button>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input
          data-testid="customer-search-input"
          placeholder="Cari nama atau nomor WhatsApp..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-11 pl-9"
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : customers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center">
          <Users className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">Belum ada pelanggan.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2" data-testid="customer-list">
          {customers.map((c) => (
            <div
              key={c.id}
              data-testid={`customer-card-${c.id}`}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_2px_10px_rgba(0,0,0,0.03)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-full bg-blue-50 font-heading text-lg font-bold text-blue-600">
                    {c.nama.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h3 className="font-heading font-semibold text-slate-900">{c.nama}</h3>
                    <p className="text-xs text-slate-500">{c.whatsapp}</p>
                    {c.alamat && <p className="mt-0.5 text-xs text-slate-400">{c.alamat}</p>}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <a href={waLink(c.whatsapp, msgKontak(c.nama))} target="_blank" rel="noreferrer" className="flex-1">
                  <Button
                    variant="outline"
                    size="sm"
                    data-testid={`customer-wa-${c.id}`}
                    className="w-full gap-1.5 border-green-200 text-green-700 hover:bg-green-50"
                  >
                    <MessageCircle className="h-4 w-4" /> WhatsApp
                  </Button>
                </a>
                <Button variant="outline" size="sm" data-testid={`customer-detail-${c.id}`} onClick={() => setDetail(c)}>
                  Riwayat
                </Button>
                <Button variant="outline" size="icon" className="h-9 w-9" data-testid={`customer-edit-${c.id}`} onClick={() => openEdit(c)}>
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9 text-red-600 hover:bg-red-50"
                  data-testid={`customer-delete-${c.id}`}
                  onClick={() => setDeleteId(c.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">{editing ? "Edit Pelanggan" : "Tambah Pelanggan"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Nama Lengkap</Label>
              <Input data-testid="customer-nama-input" value={form.nama} onChange={(e) => setForm({ ...form, nama: e.target.value })} className="mt-1" />
            </div>
            <div>
              <Label>Nomor WhatsApp</Label>
              <Input data-testid="customer-wa-input" value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} placeholder="08xxxxxxxxxx" className="mt-1" />
            </div>
            <div>
              <Label>Alamat</Label>
              <Textarea data-testid="customer-alamat-input" value={form.alamat} onChange={(e) => setForm({ ...form, alamat: e.target.value })} className="mt-1" />
            </div>
            <div>
              <Label>Nomor Identitas (KTP/SIM)</Label>
              <Input data-testid="customer-ktp-input" value={form.nomor_identitas} onChange={(e) => setForm({ ...form, nomor_identitas: e.target.value })} className="mt-1" />
            </div>
            <div>
              <Label>Catatan</Label>
              <Textarea data-testid="customer-catatan-input" value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Batal</Button>
            <Button
              data-testid="customer-save-button"
              className="bg-blue-600 hover:bg-blue-700"
              disabled={saveMut.isPending || !form.nama || !form.whatsapp}
              onClick={() => saveMut.mutate(form)}
            >
              {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail + history */}
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">Detail & Riwayat Rental</DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-4" data-testid="customer-detail-content">
              <div className="rounded-lg border border-slate-100 bg-slate-50 p-4">
                <h3 className="font-heading text-lg font-semibold text-slate-900">{detail.nama}</h3>
                <div className="mt-2 space-y-1 text-sm text-slate-600">
                  <p className="flex items-center gap-2"><MessageCircle className="h-4 w-4 text-slate-400" /> {detail.whatsapp}</p>
                  {detail.alamat && <p className="flex items-center gap-2"><MapPin className="h-4 w-4 text-slate-400" /> {detail.alamat}</p>}
                  {detail.nomor_identitas && <p className="flex items-center gap-2"><CreditCard className="h-4 w-4 text-slate-400" /> {detail.nomor_identitas}</p>}
                </div>
              </div>
              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-700">Riwayat Rental ({history.length})</h4>
                <div className="space-y-2">
                  {history.length === 0 && <p className="text-sm text-slate-400">Belum ada riwayat rental.</p>}
                  {history.map((r) => (
                    <div key={r.id} className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
                      <div>
                        <div className="text-sm font-medium text-slate-800">{r.vehicle?.merek} {r.vehicle?.tipe}</div>
                        <div className="text-xs text-slate-500">{formatPeriode(r)} · {formatDurasi(r)} · {formatRupiah(r.total)}</div>
                      </div>
                      <StatusBadge status={r.status_rental} type="rental" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus pelanggan?</AlertDialogTitle>
            <AlertDialogDescription>Tindakan ini tidak dapat dibatalkan.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="customer-delete-confirm" className="bg-red-600 hover:bg-red-700" onClick={() => deleteMut.mutate(deleteId)}>
              Hapus
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
