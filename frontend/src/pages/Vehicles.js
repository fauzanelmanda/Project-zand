import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { mediaUrl, formatApiErrorDetail } from "@/lib/api";
import { formatRupiah } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Search, Pencil, Trash2, Loader2, ImagePlus, Car } from "lucide-react";

const empty = {
  merek: "", tipe: "", tahun: new Date().getFullYear(), nomor_polisi: "",
  warna: "", harga_per_hari: "", status: "Tersedia", catatan: "", foto_url: "",
};

export default function Vehicles() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("Semua");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [uploading, setUploading] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [detail, setDetail] = useState(null);

  const { data: vehicles = [], isLoading } = useQuery({
    queryKey: ["vehicles", search, statusFilter],
    queryFn: async () =>
      (await api.get("/vehicles", { params: { search: search || undefined, status: statusFilter } })).data,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["vehicles"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const saveMut = useMutation({
    mutationFn: async (payload) => {
      const body = { ...payload, tahun: Number(payload.tahun), harga_per_hari: Number(payload.harga_per_hari) };
      if (editing) return (await api.put(`/vehicles/${editing.id}`, body)).data;
      return (await api.post("/vehicles", body)).data;
    },
    onSuccess: () => {
      toast.success(editing ? "Kendaraan berhasil diperbarui" : "Kendaraan berhasil ditambahkan");
      setDialogOpen(false);
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const statusMut = useMutation({
    mutationFn: async ({ id, status }) => (await api.patch(`/vehicles/${id}/status`, { status })).data,
    onSuccess: () => {
      toast.success("Status kendaraan diperbarui");
      invalidate();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail)),
  });

  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/vehicles/${id}`)).data,
    onSuccess: () => {
      toast.success("Kendaraan dihapus");
      setDeleteId(null);
      invalidate();
    },
    onError: (e) => {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
      setDeleteId(null);
    },
  });

  const openAdd = () => {
    setEditing(null);
    setForm(empty);
    setDialogOpen(true);
  };
  const openEdit = (v) => {
    setEditing(v);
    setForm({ ...v });
    setDialogOpen(true);
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm((f) => ({ ...f, foto_url: data.url }));
      toast.success("Foto diunggah");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">Kendaraan</h1>
          <p className="mt-1 text-sm text-slate-500">Kelola armada kendaraan rental Anda.</p>
        </div>
        <Button data-testid="add-vehicle-button" onClick={openAdd} className="gap-2 bg-blue-600 hover:bg-blue-700">
          <Plus className="h-4 w-4" /> Tambah Kendaraan
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            data-testid="vehicle-search-input"
            placeholder="Cari merek, tipe, atau nomor polisi..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-11 pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger data-testid="vehicle-status-filter" className="h-11 sm:w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Semua">Semua Status</SelectItem>
            <SelectItem value="Tersedia">Tersedia</SelectItem>
            <SelectItem value="Disewa">Disewa</SelectItem>
            <SelectItem value="Maintenance">Maintenance</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-xl" />
          ))}
        </div>
      ) : vehicles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center">
          <Car className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm text-slate-500">Tidak ada kendaraan ditemukan.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="vehicle-list">
          {vehicles.map((v) => (
            <div
              key={v.id}
              data-testid={`vehicle-card-${v.id}`}
              className="group overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_2px_10px_rgba(0,0,0,0.03)] transition-transform duration-200 hover:-translate-y-1"
            >
              <div className="relative h-40 w-full overflow-hidden bg-slate-100">
                {v.foto_url ? (
                  <img src={mediaUrl(v.foto_url)} alt={v.tipe} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-slate-300">
                    <Car className="h-10 w-10" />
                  </div>
                )}
                <div className="absolute right-3 top-3">
                  <StatusBadge status={v.status} type="vehicle" testid={`vehicle-status-${v.id}`} />
                </div>
              </div>
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-heading text-base font-semibold text-slate-900">
                      {v.merek} {v.tipe}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {v.tahun} · {v.warna} · {v.nomor_polisi}
                    </p>
                  </div>
                </div>
                <div className="mt-3 text-lg font-bold text-blue-600">
                  {formatRupiah(v.harga_per_hari)}
                  <span className="text-xs font-normal text-slate-400"> /hari</span>
                </div>

                <div className="mt-4">
                  <Label className="text-xs text-slate-400">Ubah Status</Label>
                  <Select value={v.status} onValueChange={(status) => statusMut.mutate({ id: v.id, status })}>
                    <SelectTrigger data-testid={`vehicle-status-select-${v.id}`} className="mt-1 h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Tersedia">Tersedia</SelectItem>
                      <SelectItem value="Disewa">Disewa</SelectItem>
                      <SelectItem value="Maintenance">Maintenance</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="mt-4 flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    data-testid={`vehicle-detail-${v.id}`}
                    onClick={() => setDetail(v)}
                  >
                    Detail
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9"
                    data-testid={`vehicle-edit-${v.id}`}
                    onClick={() => openEdit(v)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9 text-red-600 hover:bg-red-50 hover:text-red-700"
                    data-testid={`vehicle-delete-${v.id}`}
                    onClick={() => setDeleteId(v.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">
              {editing ? "Edit Kendaraan" : "Tambah Kendaraan"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Foto Kendaraan</Label>
              <div className="mt-1.5 flex items-center gap-4">
                <div className="h-20 w-28 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                  {form.foto_url ? (
                    <img src={mediaUrl(form.foto_url)} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full items-center justify-center text-slate-300">
                      <ImagePlus className="h-6 w-6" />
                    </div>
                  )}
                </div>
                <label className="cursor-pointer">
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    data-testid="vehicle-photo-input"
                    onChange={handleUpload}
                  />
                  <span className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                    {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                    Unggah Foto
                  </span>
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Merek</Label>
                <Input data-testid="vehicle-merek-input" value={form.merek} onChange={(e) => setForm({ ...form, merek: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Tipe/Model</Label>
                <Input data-testid="vehicle-tipe-input" value={form.tipe} onChange={(e) => setForm({ ...form, tipe: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Tahun</Label>
                <Input type="number" data-testid="vehicle-tahun-input" value={form.tahun} onChange={(e) => setForm({ ...form, tahun: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Nomor Polisi</Label>
                <Input data-testid="vehicle-nopol-input" value={form.nomor_polisi} onChange={(e) => setForm({ ...form, nomor_polisi: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Warna</Label>
                <Input data-testid="vehicle-warna-input" value={form.warna} onChange={(e) => setForm({ ...form, warna: e.target.value })} className="mt-1" />
              </div>
              <div>
                <Label>Harga /hari</Label>
                <Input type="number" data-testid="vehicle-harga-input" value={form.harga_per_hari} onChange={(e) => setForm({ ...form, harga_per_hari: e.target.value })} className="mt-1" />
              </div>
            </div>
            <div>
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(status) => setForm({ ...form, status })}>
                <SelectTrigger data-testid="vehicle-form-status" className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Tersedia">Tersedia</SelectItem>
                  <SelectItem value="Disewa">Disewa</SelectItem>
                  <SelectItem value="Maintenance">Maintenance</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Catatan</Label>
              <Textarea data-testid="vehicle-catatan-input" value={form.catatan} onChange={(e) => setForm({ ...form, catatan: e.target.value })} className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Batal</Button>
            <Button
              data-testid="vehicle-save-button"
              className="bg-blue-600 hover:bg-blue-700"
              disabled={saveMut.isPending || !form.merek || !form.tipe || !form.nomor_polisi || !form.harga_per_hari}
              onClick={() => saveMut.mutate(form)}
            >
              {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Simpan"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-heading">Detail Kendaraan</DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-3" data-testid="vehicle-detail-content">
              <div className="h-44 w-full overflow-hidden rounded-lg bg-slate-100">
                {detail.foto_url && <img src={mediaUrl(detail.foto_url)} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="grid grid-cols-2 gap-y-2 text-sm">
                <span className="text-slate-400">Merek</span><span className="font-medium text-slate-800">{detail.merek}</span>
                <span className="text-slate-400">Tipe</span><span className="font-medium text-slate-800">{detail.tipe}</span>
                <span className="text-slate-400">Tahun</span><span className="font-medium text-slate-800">{detail.tahun}</span>
                <span className="text-slate-400">Nomor Polisi</span><span className="font-medium text-slate-800">{detail.nomor_polisi}</span>
                <span className="text-slate-400">Warna</span><span className="font-medium text-slate-800">{detail.warna}</span>
                <span className="text-slate-400">Harga/hari</span><span className="font-medium text-blue-600">{formatRupiah(detail.harga_per_hari)}</span>
                <span className="text-slate-400">Status</span><span><StatusBadge status={detail.status} /></span>
              </div>
              {detail.catatan && <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{detail.catatan}</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Hapus kendaraan?</AlertDialogTitle>
            <AlertDialogDescription>Tindakan ini tidak dapat dibatalkan.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction
              data-testid="vehicle-delete-confirm"
              className="bg-red-600 hover:bg-red-700"
              onClick={() => deleteMut.mutate(deleteId)}
            >
              Hapus
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
