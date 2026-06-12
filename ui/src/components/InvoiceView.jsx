// Format angka ke "Rp 6.400.000" (format Indonesia)
const rp = (amount) =>
  amount != null ? 'Rp ' + Number(amount).toLocaleString('id-ID') : '-'

export default function InvoiceView({ groundTruth }) {
  if (!groundTruth) return null
  const gt = groundTruth

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">

      {/* Kiri: gambar invoice */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
          <h2 className="font-semibold text-slate-700 text-sm">Gambar Faktur (output asli)</h2>
        </div>
        <div className="p-4">
          <img
            src="/images/invoice_original.png"
            alt="Invoice"
            className="w-full rounded border border-slate-200"
          />
        </div>
      </div>

      {/* Kanan: data terstruktur */}
      <div className="flex flex-col gap-4">

        {/* Meta */}
        <Card title="Informasi Faktur">
          <Row label="No. Faktur"  value={gt.nomor_faktur} mono />
          <Row label="Tanggal"     value={gt.tanggal} />
          <Row label="Jatuh Tempo" value={gt.jatuh_tempo} />
        </Card>

        {/* Penjual */}
        <Card title="Penjual">
          <Row label="Nama"   value={gt.nama_penjual} />
          <Row label="NPWP"   value={gt.npwp_penjual} mono />
          <Row label="Alamat" value={gt.alamat_penjual} />
        </Card>

        {/* Pembeli */}
        <Card title="Pembeli">
          <Row label="Nama"   value={gt.nama_pembeli} />
          <Row label="NPWP"   value={gt.npwp_pembeli} mono />
          <Row label="Alamat" value={gt.alamat_pembeli} />
        </Card>

        {/* Tabel item */}
        <Card title={`Item (${gt.items?.length ?? 0} barang)`}>
          <div className="overflow-x-auto -mx-4 px-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 uppercase border-b border-slate-100">
                  <th className="text-left py-2 pr-3 font-medium">No</th>
                  <th className="text-left py-2 pr-3 font-medium">Deskripsi</th>
                  <th className="text-right py-2 pr-3 font-medium">Qty</th>
                  <th className="text-left py-2 pr-3 font-medium">Sat</th>
                  <th className="text-right py-2 pr-3 font-medium">Harga Satuan</th>
                  <th className="text-right py-2 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {gt.items?.map(item => (
                  <tr key={item.nomor} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 pr-3 text-slate-400">{item.nomor}</td>
                    <td className="py-2 pr-3 text-slate-700">{item.deskripsi}</td>
                    <td className="py-2 pr-3 text-right text-slate-600">{item.kuantitas}</td>
                    <td className="py-2 pr-3 text-slate-500">{item.satuan}</td>
                    <td className="py-2 pr-3 text-right font-mono text-slate-600">
                      {rp(item.harga_satuan)}
                    </td>
                    <td className="py-2 text-right font-mono text-slate-700 font-medium">
                      {rp(item.total_harga)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Totals */}
        <Card title="Ringkasan Pembayaran">
          <Row label="Subtotal" value={rp(gt.subtotal)} mono />
          <Row label="PPN (11%)" value={rp(gt.ppn)} mono />
          <div className="flex justify-between items-center pt-2 mt-2 border-t border-slate-200">
            <span className="font-bold text-slate-800">TOTAL</span>
            <span className="font-bold text-blue-600 font-mono text-lg">{rp(gt.total)}</span>
          </div>
          <p className="text-xs text-slate-500 mt-2 italic">
            {gt.terbilang} Rupiah
          </p>
        </Card>

      </div>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function Card({ title, children }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200">
      <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
        <h3 className="font-semibold text-slate-700 text-sm">{title}</h3>
      </div>
      <div className="px-4 py-3 space-y-2">{children}</div>
    </div>
  )
}

function Row({ label, value, mono = false }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className={`text-slate-800 text-right ${mono ? 'font-mono' : ''}`}>{value ?? '-'}</span>
    </div>
  )
}
