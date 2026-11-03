import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import HeatMap, { type MapLayer } from "../components/HeatMap";
import { Card, ErrorText, Loading, StatusBadge, Table } from "../components/ui";
import { c, pct } from "../format";
import type { HeatmapFC } from "../types";
import { Link } from "react-router-dom";

export default function MapPage() {
  const [layer, setLayer] = useState<MapLayer>("status");
  const q = useQuery({ queryKey: ["heatmap", "combined"], queryFn: () => api<HeatmapFC>("/heatmap?layer=combined") });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Peta panas</h1>
        <div className="inline-flex rounded-md border border-gray-300 bg-white text-sm" role="tablist">
          {(
            [
              ["status", "Status dan suhu udara (sensor)"],
              ["lst", "Suhu permukaan (satelit)"],
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              role="tab"
              aria-selected={layer === k}
              onClick={() => setLayer(k)}
              className={`px-3 py-1.5 ${layer === k ? "bg-brand-teal text-white" : "hover:bg-gray-50"} first:rounded-l-md last:rounded-r-md`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>
      {layer === "lst" && (
        <p className="text-xs text-ink-2">
          Suhu permukaan tanah (LST) dari citra Landsat menggambarkan panas atap, jalan, dan tanah. Nilainya bukan suhu
          udara, tidak real-time, dan tidak dipakai untuk peringatan.
        </p>
      )}
      <ErrorText error={q.error} />
      {q.data ? <HeatMap data={q.data} layer={layer} height={560} /> : <Loading />}

      {q.data && (
        <Card title="Tabel per RW">
          <Table head={["RW", "Status", "Indeks panas", "Suhu udara", "Kelembapan", "Sumber", "LST (permukaan)"]}>
            {[...q.data.features]
              .sort((a, b) => (b.properties.heat_index_c ?? -99) - (a.properties.heat_index_c ?? -99))
              .map(({ properties: p }) => (
                <tr key={p.rw_id}>
                  <td className="px-2 py-1.5">
                    <Link to={`/rw/${p.rw_id}`} className="hover:underline">{p.name}</Link>
                  </td>
                  <td className="px-2 py-1.5"><StatusBadge status={p.status} /></td>
                  <td className="px-2 py-1.5 tabular-nums">{c(p.heat_index_c)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{c(p.air_temp_c)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{pct(p.rh_pct)}</td>
                  <td className="px-2 py-1.5 text-xs text-ink-2">
                    {p.tier === "A" ? `${p.n_sensors} sensor` : p.tier === "B" ? "perkiraan (sensor terdekat)" : "tidak ada sensor"}
                  </td>
                  <td className="px-2 py-1.5 tabular-nums">{c(p.lst_c)}</td>
                </tr>
              ))}
          </Table>
        </Card>
      )}
    </div>
  );
}
