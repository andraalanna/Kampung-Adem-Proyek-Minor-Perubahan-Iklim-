import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import HeatMap from "../components/HeatMap";
import { Card, Empty, ErrorText, Loading, StatusBadge } from "../components/ui";
import { c, dt, STATUS_META, STATUS_ORDER } from "../format";
import type { AlertItem, HeatmapFC, Summary } from "../types";

export default function Dashboard() {
  const sum = useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/dashboard/summary") });
  const map = useQuery({ queryKey: ["heatmap", "combined"], queryFn: () => api<HeatmapFC>("/heatmap?layer=combined") });
  const alerts = useQuery({
    queryKey: ["alerts", "active"],
    queryFn: () => api<{ items: AlertItem[] }>("/alerts?status=active&limit=20"),
  });

  if (sum.isLoading) return <Loading />;
  if (sum.error) return <ErrorText error={sum.error} />;
  const s = sum.data!;
  const activeWa = alerts.data?.items.filter((a) => a.level !== "WASPADA") ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Ringkasan</h1>
        <span className="text-xs text-ink-3">Data per {dt(s.as_of)} · diperbarui otomatis tiap menit</span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {STATUS_ORDER.map((st) => (
          <div key={st} className="rounded-lg border border-gray-200 bg-surface p-3">
            <div className="flex items-center gap-1.5 text-xs text-ink-2">
              <span
                className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold"
                style={{ background: STATUS_META[st].color, color: STATUS_META[st].text }}
                aria-hidden
              >
                {STATUS_META[st].icon}
              </span>
              {STATUS_META[st].label}
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{s.rw_by_status[st] ?? 0}</div>
            <div className="text-xs text-ink-3">RW</div>
          </div>
        ))}
        <div className="rounded-lg border border-gray-200 bg-surface p-3">
          <div className="text-xs text-ink-2">Pembanding BMKG</div>
          <div className="mt-1 text-2xl font-semibold">{s.bmkg_reference ? c(s.bmkg_reference.temp_c) : "-"}</div>
          <div className="text-xs text-ink-3">{s.bmkg_reference ? s.bmkg_reference.station : "Belum terhubung"}</div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Peta panas per RW" className="lg:col-span-2" actions={<Link to="/peta" className="text-xs text-brand-teal underline">Buka peta penuh</Link>}>
          {map.data ? <HeatMap data={map.data} height={420} /> : <Loading />}
        </Card>

        <div className="space-y-4">
          <Card title={`Peringatan aktif (${activeWa.length})`}>
            {activeWa.length === 0 ? (
              <Empty>Tidak ada peringatan SIAGA atau AWAS saat ini.</Empty>
            ) : (
              <ul className="space-y-2">
                {activeWa.map((a) => (
                  <li key={a.id} className="rounded border border-gray-100 p-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <Link to={`/rw/${a.rw_id}`} className="font-medium hover:underline">{a.rw_name}</Link>
                      <StatusBadge status={a.level} />
                    </div>
                    <div className="mt-1 text-xs text-ink-2">
                      Indeks panas puncak {c(a.peak_hi_c)} · sejak {dt(a.started_at)}
                    </div>
                    <div className="text-xs text-ink-3">
                      WA: {a.notifications.sent} terkirim, {a.notifications.held} ditahan, {a.notifications.failed} gagal
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="RW terpanas">
            {s.hottest_rw ? (
              <Link to={`/rw/${s.hottest_rw.rw_id}`} className="block hover:underline">
                <div className="text-sm">{s.hottest_rw.name}</div>
                <div className="text-2xl font-semibold">{c(s.hottest_rw.heat_index_c)}</div>
                <div className="text-xs text-ink-3">indeks panas (dari sensor)</div>
              </Link>
            ) : (
              <Empty>Belum ada data sensor.</Empty>
            )}
          </Card>

          <Card title="Kesehatan sensor">
            <div className="grid grid-cols-3 text-center text-sm">
              <div><div className="text-xl font-semibold">{s.sensors.online}</div><div className="text-xs text-ink-3">Online</div></div>
              <div><div className="text-xl font-semibold">{s.sensors.late}</div><div className="text-xs text-ink-3">Terlambat</div></div>
              <div><div className="text-xl font-semibold">{s.sensors.offline}</div><div className="text-xs text-ink-3">Offline</div></div>
            </div>
            <div className="mt-2 text-xs text-ink-3">
              Pesan WA hari ini: {s.wa_sent_today}
              {s.wa_dry_run && " (mode simulasi, tidak benar-benar dikirim)"}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
