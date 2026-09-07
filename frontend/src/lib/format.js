export const formatRupiah = (n) => {
  const num = Number(n || 0);
  return "Rp " + num.toLocaleString("id-ID");
};

export const formatTanggal = (s) => {
  if (!s) return "-";
  const d = new Date(s.length <= 10 ? s + "T00:00:00" : s);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
};

export const formatDurasi = (r) => {
  if (r.tipe_sewa === "24 Jam") return `${r.jumlah_hari} × 24 Jam`;
  return `${r.jumlah_hari} hari`;
};

export const formatPeriode = (r) => {
  if (r.tipe_sewa === "24 Jam") {
    return `${formatTanggal(r.tanggal_mulai)} ${r.waktu_mulai || ""} → ${formatTanggal(r.tanggal_kembali)} ${r.waktu_kembali || ""}`;
  }
  return `${formatTanggal(r.tanggal_mulai)} → ${formatTanggal(r.tanggal_kembali)}`;
};

export const toWaNumber = (wa) => {
  let n = (wa || "").replace(/[^0-9]/g, "");
  if (n.startsWith("0")) n = "62" + n.slice(1);
  if (n.startsWith("620")) n = "62" + n.slice(3);
  return n;
};

export const waLink = (wa, message) =>
  `https://wa.me/${toWaNumber(wa)}?text=${encodeURIComponent(message)}`;

// Message generators
export const msgKonfirmasi = (r) =>
  `Halo ${r.customer?.nama}, booking Anda telah dikonfirmasi.\n\n` +
  `No. Transaksi: ${r.transaksi_id}\n` +
  `Kendaraan: ${r.vehicle?.merek} ${r.vehicle?.tipe} (${r.vehicle?.nomor_polisi})\n` +
  `Tipe Sewa: ${r.tipe_sewa || "Harian"}\n` +
  `Periode: ${formatPeriode(r)}\n` +
  `Durasi: ${formatDurasi(r)}\n` +
  `Total: ${formatRupiah(r.total)}\n\nTerima kasih telah mempercayai ARMI Rental.`;

export const msgPengingatBayar = (r) =>
  `Halo ${r.customer?.nama}, ini pengingat pembayaran untuk transaksi ${r.transaksi_id}.\n\n` +
  `Kendaraan: ${r.vehicle?.merek} ${r.vehicle?.tipe}\n` +
  `Total: ${formatRupiah(r.total)}\n` +
  `Status pembayaran: ${r.status_pembayaran}\n\nMohon segera menyelesaikan pembayaran. Terima kasih.`;

export const msgPengingatKembali = (r) =>
  `Halo ${r.customer?.nama}, mengingatkan bahwa kendaraan ${r.vehicle?.merek} ${r.vehicle?.tipe} ` +
  `(${r.vehicle?.nomor_polisi}) harus dikembalikan pada ${formatTanggal(r.tanggal_kembali)}.\n\n` +
  `Terima kasih telah menggunakan ARMI Rental.`;

export const msgKontak = (nama) => `Halo ${nama}, `;

export const invoiceUrl = (id) => `${process.env.REACT_APP_BACKEND_URL}/api/invoices/${id}`;

export const msgInvoice = (r) =>
  `Halo ${r.customer?.nama}, berikut invoice rental Anda dari ARMI Rental.\n\n` +
  `No. Invoice: ${r.transaksi_id}\n` +
  `Kendaraan: ${r.vehicle?.merek} ${r.vehicle?.tipe} (${r.vehicle?.nomor_polisi})\n` +
  `Tipe Sewa: ${r.tipe_sewa || "Harian"}\n` +
  `Periode: ${formatPeriode(r)}\n` +
  `Durasi: ${formatDurasi(r)}\n` +
  `Total: ${formatRupiah(r.total)}\n` +
  `Sudah Dibayar: ${formatRupiah(r.total_paid)}\n` +
  `Sisa Pembayaran: ${formatRupiah(r.sisa)}\n` +
  `Status: ${r.status_pembayaran}\n\n` +
  `Invoice (PDF): ${invoiceUrl(r.id)}\n\nTerima kasih telah mempercayai ARMI Rental.`;
