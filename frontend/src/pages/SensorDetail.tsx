import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import TimeChart from "../components/HiChart";
import { btnCls, Card, ErrorText, Field, inputCls, Loading, Table } from "../components/ui";
import { c, dt, pct } from "../format";
import type { Sensor } from "../types";
import { NodeStatus } from "./Sensors";

type Pt = {
  ts: string;
  temp_c: number | null;
  rh_pct: number | null;
  heat_index_c: number | null;
  qc_flag: "ok" | "suspect" | "invalid";
  qc_reasons: string | null;
};

const QC_REASON: Record<string, string> = {
  neighbor: "beda jauh dari sensor tetangga",
  spike: "lonjakan mendadak",
  stuck: "nilai macet",
  condensation: "kondensasi",
  low_battery: "baterai lemah",
  temp_range: "suhu di luar rentang",
  rh_range: "kelembapan di luar rentang",
  missing: "bacaan hilang",
};
interface Maint {
  id: number;
  type: string;
  description: string;
  resolved: boolean;
  performed_at: string | null;
  created_at: string;
}

export default function SensorDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["sensor", id], queryFn: () => api<Sensor>(`/sensors/${id}`) });
  const to = new Date();
  const from = new Date(to.getTime() - 24 * 3600_000);
  const r = useQuery({
    queryKey: ["readings", id],
    queryFn: () =>
      api<{ points: Pt[] }>(
        `/sensors/${id}/readings?interval=raw&from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`,
      ),
  });
  const m = useQuery({
    queryKey: ["maint", id],
    queryFn: () => api<{ items: Maint[] }>(`/maintenance-logs?node_id=${id}`),
    enabled: can("admin", "teknis"),
  });

  const [type, setType] = useState("cleaning");
  const [desc, setDesc] = useState("");
  const add = useMutation({
    mutationFn: () =>
      api("/maintenance-logs", {
        method: "POST",
        body: JSON.stringify({ node_id: id, type, description: desc, performed_at: new Date().toISOString() }),
      }),
    onSuccess: () => {
      setDesc("");
      qc.invalidateQueries({ queryKey: ["maint", id] });
    },
  });

  if (s.isLoading) return <Loading />;
  if (s.error) return <ErrorText error={s.error} />;
  const n = s.data!;
  const raw = r.data?.points ?? [];
  // Technicians see every reading. Invalid ones are blanked (shown as gaps), suspect ones kept.
  const pts = raw.map((p) => (p.qc_flag === "invalid" ? { ts: p.ts } : p));
  const counts = { ok: 0, suspect: 0, invalid: 0 };
  const reasons = new Map<string, number>();
  for (const p of raw) {
    counts[p.qc_flag]++;
    for (const r of p.qc_reasons?.split(",") ?? []) reasons.set(r, (reasons.get(r) ?? 0) + 1);
  }

  return (
    <div className="space-y-4">
      <div className="text-sm text-ink-3">
        <Link to="/sensor" className="hover:underline">Sensor</Link> / {n.id}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <h1 className="text-lg font-semibold">{n.name}</h1>
          <div className="mt-1 flex items-center gap-2">
            <NodeStatus status={n.status} />
            <span className="font-mono text-xs text-ink-3">{n.dev_eui}</span>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-sm">
            <dt className="text-ink-2">Terakhir terlihat</dt><dd className="text-right">{dt(n.last_seen)}</dd>
            <dt className="text-ink-2">Suhu</dt><dd className="text-right">{c(n.last_reading?.temp_c)}</dd>
            <dt className="text-ink-2">Kelembapan</dt><dd className="text-right">{pct(n.last_reading?.rh_pct)}</dd>
            <dt className="text-ink-2">Flag QC</dt><dd className="text-right">{n.last_reading?.qc_flag ?? "-"}</dd>
            <dt className="text-ink-2">Baterai</dt><dd className="text-right">{n.battery_v?.toFixed(2) ?? "-"} V</dd>
            <dt className="text-ink-2">RSSI / SNR</dt><dd className="text-right">{n.rssi ?? "-"} dBm / {n.snr ?? "-"} dB</dd>
            <dt className="text-ink-2">Tinggi pasang</dt><dd className="text-right">{n.mount_height_m ?? "-"} m</dd>
            <dt className="text-ink-2">Offset kalibrasi</dt><dd className="text-right">{n.offset_temp} °C / {n.offset_rh} %</dd>
            <dt className="text-ink-2">Firmware</dt><dd className="text-right">{n.firmware_version ?? "-"}</dd>
          </dl>
        </Card>
        <Card className="md:col-span-2" title="24 jam terakhir (semua bacaan 5 menit, termasuk yang ditandai QC)">
          <p className="mb-3 text-xs text-ink-2">
            {raw.length} bacaan: {counts.ok} lolos QC, {counts.suspect} dicurigai, {counts.invalid} tidak valid.
            {reasons.size > 0 &&
              ` Alasan: ${[...reasons].map(([k, v]) => `${QC_REASON[k] ?? k} (${v})`).join(", ")}.`}
            {counts.suspect + counts.invalid > 0 && " Hanya bacaan lolos QC yang dipakai untuk status RW."}
          </p>
          <div className="space-y-4">
            <TimeChart points={pts} field="temp_c" label="Suhu udara (°C)" stepMs={300_000} color="#3a6b7e" height={170} />
            <TimeChart points={pts} field="rh_pct" label="Kelembapan relatif (%)" stepMs={300_000} unit="%" color="#3a6b7e" height={150} />
          </div>
        </Card>
      </div>

      {can("admin", "teknis") && (
        <Card title="Catatan perawatan dan tiket">
          <form
            className="mb-4 grid gap-2 sm:grid-cols-[160px_1fr_auto]"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              add.mutate();
            }}
          >
            <Field label="Jenis">
              <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>
                <option value="cleaning">Pembersihan shield</option>
                <option value="battery">Ganti baterai</option>
                <option value="replace">Ganti node</option>
                <option value="calibration">Kalibrasi</option>
                <option value="antenna">Antena</option>
                <option value="other">Lainnya</option>
              </select>
            </Field>
            <Field label="Keterangan">
              <input className={inputCls} value={desc} onChange={(e) => setDesc(e.target.value)} required minLength={3} />
            </Field>
            <div className="flex items-end">
              <button className={btnCls} disabled={add.isPending}>Catat</button>
            </div>
          </form>
          <ErrorText error={add.error} />
          <Table head={["Waktu", "Jenis", "Keterangan", "Status"]}>
            {(m.data?.items ?? []).map((x) => (
              <tr key={x.id}>
                <td className="px-2 py-1.5 whitespace-nowrap">{dt(x.performed_at ?? x.created_at)}</td>
                <td className="px-2 py-1.5">{x.type.startsWith("ticket") ? "Tiket otomatis" : x.type}</td>
                <td className="px-2 py-1.5">{x.description}</td>
                <td className="px-2 py-1.5 text-xs">{x.resolved ? "Selesai" : "Terbuka"}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </div>
  );
}
