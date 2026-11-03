import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import TimeChart from "../components/HiChart";
import { Card, ErrorText, Loading, StatusBadge, Table } from "../components/ui";
import { c, date, dt, pct } from "../format";
import type { AlertItem, RwDetail as RwDetailT, Threshold } from "../types";

export default function RwDetail() {
  const { id } = useParams();
  const [hours, setHours] = useState(24);
  const q = useQuery({ queryKey: ["rw", id, hours], queryFn: () => api<RwDetailT>(`/regions/rw/${id}?hours=${hours}`) });
  const th = useQuery({ queryKey: ["thresholds"], queryFn: () => api<{ items: Threshold[] }>("/thresholds") });
  const alerts = useQuery({
    queryKey: ["alerts", "rw", id],
    queryFn: () => api<{ items: AlertItem[] }>(`/alerts?rw_id=${id}&limit=20`),
  });

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorText error={q.error} />;
  const d = q.data!;
  const l = d.latest;
  const globalTh = (th.data?.items ?? []).filter((t) => t.rw_id === null || t.rw_id === d.id);

  return (
    <div className="space-y-4">
      <div className="text-sm text-ink-3">
        <Link to="/peta" className="hover:underline">Peta</Link> / {d.name}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <h1 className="text-lg font-semibold">{d.name}</h1>
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge status={d.status} estimate={!!l && l.tier !== "A"} />
            {d.level_since && <span className="text-xs text-ink-3">sejak {dt(d.level_since)}</span>}
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-ink-2">Indeks panas</dt>
            <dd className="text-right text-lg font-semibold tabular-nums">{c(l?.heat_index_c)}</dd>
            <dt className="text-ink-2">Suhu udara</dt>
            <dd className="text-right tabular-nums">{c(l?.air_temp_c)}</dd>
            <dt className="text-ink-2">Kelembapan</dt>
            <dd className="text-right tabular-nums">{pct(l?.rh_pct)}</dd>
            <dt className="text-ink-2">Sensor aktif</dt>
            <dd className="text-right">{d.active_sensors}</dd>
            <dt className="text-ink-2">Warga rentan</dt>
            <dd className="text-right">{d.vulnerable_count ?? "-"}</dd>
          </dl>
          <p className="mt-3 text-xs text-ink-3">Pengukuran terakhir: {dt(l?.ts)}</p>
          {l?.lst_c != null && (
            <p className="mt-2 text-xs text-ink-2">
              Suhu permukaan (satelit, bukan suhu udara): {c(l.lst_c)}, citra {date(l.lst_scene_date)}
            </p>
          )}
          {(d.status === "SIAGA" || d.status === "AWAS") && (
            <div className="mt-4 rounded bg-brand-amber/15 p-3 text-sm">
              <div className="font-medium">Yang perlu dilakukan</div>
              <ul className="mt-1 list-disc pl-5 text-ink-2">
                <li>Cek lansia yang tinggal sendiri</li>
                <li>Ingatkan warga minum air</li>
                <li>Kurangi aktivitas di bawah matahari</li>
                <li>Jika ada warga pusing berat, bingung, atau pingsan, hubungi puskesmas atau 112</li>
              </ul>
              <p className="mt-2 text-xs text-ink-3">
                Informasi panas ekstrem tingkat lingkungan dari sensor, bukan diagnosis kesehatan.
              </p>
            </div>
          )}
        </Card>

        <Card
          className="md:col-span-2"
          title="Indeks panas RW"
          actions={
            <select className="rounded border border-gray-300 px-2 py-1 text-xs" value={hours} onChange={(e) => setHours(+e.target.value)}>
              <option value={24}>24 jam</option>
              <option value={168}>7 hari</option>
            </select>
          }
        >
          <TimeChart
            points={d.history}
            field="heat_index_c"
            label="Indeks panas (°C), per 10 menit"
            stepMs={10 * 60_000}
            thresholds={globalTh.filter((t) => t.level !== "WASPADA")}
            color="#3a6b7e"
            height={280}
          />
        </Card>
      </div>

      <Card title="Riwayat peringatan">
        <Table head={["Level", "Mulai", "Selesai", "Alasan", "Puncak", "WA"]}>
          {(alerts.data?.items ?? []).map((a) => (
            <tr key={a.id}>
              <td className="px-2 py-1.5"><StatusBadge status={a.level} /></td>
              <td className="px-2 py-1.5">{dt(a.started_at)}</td>
              <td className="px-2 py-1.5">{a.resolved_at ? dt(a.resolved_at) : "Aktif"}</td>
              <td className="px-2 py-1.5 text-xs text-ink-2">{a.trigger.rule}</td>
              <td className="px-2 py-1.5 tabular-nums">{c(a.peak_hi_c)}</td>
              <td className="px-2 py-1.5 text-xs">{a.notifications.sent} terkirim / {a.notifications.held} ditahan</td>
            </tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}
