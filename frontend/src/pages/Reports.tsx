import { useState } from "react";
import { ApiError, authFetch } from "../api";
import { btnCls, Card, ErrorText, Field, inputCls } from "../components/ui";

export default function Reports() {
  const now = new Date();
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);
  const [error, setError] = useState<unknown>(null);

  const download = async () => {
    setError(null);
    try {
      const res = await authFetch(`/reports/monthly?month=${month}&format=csv`);
      if (!res.ok) throw new ApiError(res.status, "Gagal mengunduh laporan");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `laporan-kampung-adem-${month}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Laporan bulanan</h1>
      <Card>
        <p className="mb-3 max-w-2xl text-sm text-ink-2">
          Per RW: jumlah jam pada status Waspada, Siaga, Awas, dan tanpa data; indeks panas maksimum dari sensor;
          kelengkapan data; dan jumlah peringatan WhatsApp.
        </p>
        <div className="flex items-end gap-3">
          <Field label="Bulan">
            <input className={inputCls} type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          </Field>
          <button className={btnCls} onClick={download}>Unduh CSV</button>
        </div>
        <ErrorText error={error} />
      </Card>
    </div>
  );
}
