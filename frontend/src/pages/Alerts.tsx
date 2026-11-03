import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { btnGhostCls, Card, Empty, ErrorText, Loading, StatusBadge, Table } from "../components/ui";
import { c, dt } from "../format";
import type { AlertItem } from "../types";

const REASON: Record<string, string> = {
  naik: "Naik level",
  histeresis: "Turun (histeresis)",
  data_terputus: "Data terputus",
  ditutup_manual: "Ditutup manual",
};

export default function AlertsPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const [level, setLevel] = useState("");
  const params = new URLSearchParams({ limit: "200", ...(status && { status }), ...(level && { level }) });
  const q = useQuery({ queryKey: ["alerts", status, level], queryFn: () => api<{ items: AlertItem[] }>(`/alerts?${params}`) });
  const close = useMutation({
    mutationFn: (id: number) => api(`/alerts/${id}/close`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Daftar peringatan</h1>
      <div className="flex flex-wrap gap-2 text-sm">
        <select className="rounded border border-gray-300 px-2 py-1" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Semua status</option>
          <option value="active">Aktif</option>
          <option value="resolved">Selesai</option>
        </select>
        <select className="rounded border border-gray-300 px-2 py-1" value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">Semua level</option>
          <option value="WASPADA">Waspada</option>
          <option value="SIAGA">Siaga</option>
          <option value="AWAS">Awas</option>
        </select>
      </div>
      <Card>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorText error={q.error} />
        ) : q.data!.items.length === 0 ? (
          <Empty>Tidak ada peringatan untuk filter ini.</Empty>
        ) : (
          <Table head={["RW", "Level", "Mulai", "Selesai", "Alasan", "Puncak", "WhatsApp", "Konfirmasi", ""]}>
            {q.data!.items.map((a) => (
              <tr key={a.id}>
                <td className="px-2 py-1.5"><Link to={`/rw/${a.rw_id}`} className="hover:underline">{a.rw_name}</Link></td>
                <td className="px-2 py-1.5"><StatusBadge status={a.level} /></td>
                <td className="px-2 py-1.5 whitespace-nowrap">{dt(a.started_at)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">
                  {a.resolved_at ? (
                    <>
                      {dt(a.resolved_at)}
                      <div className="text-xs text-ink-3">{REASON[a.resolved_reason ?? ""] ?? a.resolved_reason}</div>
                    </>
                  ) : (
                    <span className="font-medium">Aktif</span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-xs text-ink-2">
                  {a.source === "auto" ? a.trigger.rule : `Manual: ${a.note ?? ""}`}
                </td>
                <td className="px-2 py-1.5 tabular-nums">{c(a.peak_hi_c)}</td>
                <td className="px-2 py-1.5 text-xs">
                  {a.notifications.sent} terkirim
                  {a.notifications.held > 0 && `, ${a.notifications.held} ditahan`}
                  {a.notifications.failed > 0 && `, ${a.notifications.failed} gagal`}
                </td>
                <td className="px-2 py-1.5 text-xs">{a.notifications.confirmed}</td>
                <td className="px-2 py-1.5">
                  {can("admin") && !a.resolved_at && (
                    <button className={`${btnGhostCls} text-xs`} onClick={() => close.mutate(a.id)}>
                      Tutup
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
