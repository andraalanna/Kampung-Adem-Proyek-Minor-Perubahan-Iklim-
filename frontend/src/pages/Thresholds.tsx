import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { btnCls, Card, ErrorText, Field, inputCls, Loading, StatusBadge, Table } from "../components/ui";
import { dt } from "../format";
import type { Threshold } from "../types";

export default function Thresholds() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [history, setHistory] = useState(false);
  const q = useQuery({
    queryKey: ["thresholds", history],
    queryFn: () => api<{ items: Threshold[] }>(`/thresholds?include_history=${history}`),
  });
  const [edit, setEdit] = useState<Threshold | null>(null);
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: (t: Threshold) =>
      api("/thresholds", {
        method: "PUT",
        body: JSON.stringify({
          rw_id: t.rw_id,
          level: t.level,
          min_value: t.min_value,
          duration_min: t.duration_min,
          min_sensors: t.min_sensors,
          exit_value: t.exit_value,
          exit_duration_min: t.exit_duration_min,
          escalate_from: t.escalate_from,
          escalate_after_min: t.escalate_after_min,
          approved_note: note,
        }),
      }),
    onSuccess: () => {
      setEdit(null);
      setNote("");
      qc.invalidateQueries({ queryKey: ["thresholds"] });
    },
  });

  const num = (k: keyof Threshold) => (e: ChangeEvent<HTMLInputElement>) =>
    setEdit((t) => (t ? { ...t, [k]: e.target.value === "" ? null : Number(e.target.value) } : t));

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Pengaturan ambang</h1>
      <p className="max-w-3xl text-sm text-ink-2">
        Ambang ini adalah ambang operasional sistem berbasis indeks panas, bukan ambang medis. Nilai awal masih usulan dan
        perlu dikaji bersama Dinkes. Setiap perubahan disimpan sebagai versi baru beserta catatan persetujuannya.
      </p>
      <Card
        actions={
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Tampilkan riwayat versi
          </label>
        }
      >
        {q.isLoading ? (
          <Loading />
        ) : (
          <Table head={["Level", "Masuk", "Keluar (histeresis)", "Min. sensor", "Eskalasi", "Versi", "Catatan", ""]}>
            {q.data?.items.map((t) => (
              <tr key={t.id} className={t.active ? "" : "text-ink-3"}>
                <td className="px-2 py-1.5"><StatusBadge status={t.level} /></td>
                <td className="px-2 py-1.5">HI ≥ {t.min_value} °C selama {t.duration_min} menit</td>
                <td className="px-2 py-1.5">HI &lt; {t.exit_value} °C selama {t.exit_duration_min} menit</td>
                <td className="px-2 py-1.5">{t.min_sensors}</td>
                <td className="px-2 py-1.5 text-xs">{t.escalate_from ? `${t.escalate_from} bertahan ${t.escalate_after_min} menit` : "-"}</td>
                <td className="px-2 py-1.5 text-xs">v{t.version}{t.active ? "" : " (lama)"}<div>{dt(t.created_at)}</div></td>
                <td className="px-2 py-1.5 text-xs">{t.approved_note}</td>
                <td className="px-2 py-1.5">
                  {can("admin") && t.active && (
                    <button className="text-xs text-brand-teal underline" onClick={() => setEdit(t)}>Ubah</button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {edit && (
        <Card title={`Versi baru ambang ${edit.level}`}>
          <form
            className="grid gap-3 sm:grid-cols-3"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              save.mutate(edit);
            }}
          >
            <Field label="Masuk: indeks panas minimal (°C)"><input className={inputCls} type="number" step="0.1" value={edit.min_value} onChange={num("min_value")} /></Field>
            <Field label="Masuk: durasi (menit, kelipatan 10)"><input className={inputCls} type="number" step="10" value={edit.duration_min} onChange={num("duration_min")} /></Field>
            <Field label="Minimal sensor melewati ambang"><input className={inputCls} type="number" value={edit.min_sensors} onChange={num("min_sensors")} /></Field>
            <Field label="Keluar: indeks panas di bawah (°C)"><input className={inputCls} type="number" step="0.1" value={edit.exit_value} onChange={num("exit_value")} /></Field>
            <Field label="Keluar: durasi (menit)"><input className={inputCls} type="number" step="10" value={edit.exit_duration_min} onChange={num("exit_duration_min")} /></Field>
            <Field label="Eskalasi setelah (menit, opsional)"><input className={inputCls} type="number" value={edit.escalate_after_min ?? ""} onChange={num("escalate_after_min")} /></Field>
            <div className="sm:col-span-3">
              <Field label="Catatan persetujuan (wajib, mis. nomor surat Dinkes)">
                <input className={inputCls} required minLength={5} value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
            </div>
            <div className="flex gap-2 sm:col-span-3">
              <button className={btnCls} disabled={save.isPending}>Simpan versi baru</button>
              <button type="button" className="text-sm" onClick={() => setEdit(null)}>Batal</button>
            </div>
          </form>
          <ErrorText error={save.error} />
        </Card>
      )}
    </div>
  );
}
