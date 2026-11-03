import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Card, ErrorText, Loading, Table } from "../components/ui";
import { c, dt, pct } from "../format";
import type { Sensor } from "../types";

export const NODE_STATUS: Record<string, { label: string; cls: string }> = {
  online: { label: "Online", cls: "bg-green-100 text-green-800" },
  late: { label: "Terlambat", cls: "bg-amber-100 text-amber-800" },
  offline: { label: "Offline", cls: "bg-red-100 text-red-800" },
  new: { label: "Baru", cls: "bg-gray-100 text-gray-700" },
};

export function NodeStatus({ status }: { status: string }) {
  const m = NODE_STATUS[status] ?? NODE_STATUS.new;
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${m.cls}`}>{m.label}</span>;
}

export default function Sensors() {
  const q = useQuery({ queryKey: ["sensors"], queryFn: () => api<{ items: Sensor[] }>("/sensors?page_size=500") });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Sensor</h1>
      <Card>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorText error={q.error} />
        ) : (
          <Table head={["ID", "Nama", "Status", "Terakhir", "Suhu", "RH", "Indeks panas", "QC", "Baterai", "RSSI"]}>
            {q.data!.items.map((s) => (
              <tr key={s.id}>
                <td className="px-2 py-1.5 font-mono text-xs">
                  <Link to={`/sensor/${s.id}`} className="hover:underline">{s.id}</Link>
                </td>
                <td className="px-2 py-1.5">{s.name}</td>
                <td className="px-2 py-1.5"><NodeStatus status={s.status} /></td>
                <td className="px-2 py-1.5 whitespace-nowrap">{dt(s.last_seen)}</td>
                <td className="px-2 py-1.5 tabular-nums">{c(s.last_reading?.temp_c)}</td>
                <td className="px-2 py-1.5 tabular-nums">{pct(s.last_reading?.rh_pct)}</td>
                <td className="px-2 py-1.5 tabular-nums">{c(s.last_reading?.heat_index_c)}</td>
                <td className="px-2 py-1.5 text-xs">{s.last_reading?.qc_flag ?? "-"}</td>
                <td className={`px-2 py-1.5 tabular-nums ${s.battery_v != null && s.battery_v < 3.4 ? "font-semibold text-red-700" : ""}`}>
                  {s.battery_v != null ? `${s.battery_v.toFixed(2)} V` : "-"}
                </td>
                <td className="px-2 py-1.5 tabular-nums">{s.rssi ?? "-"}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
