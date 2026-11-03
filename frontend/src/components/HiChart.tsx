import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { c, dt, time, withGaps } from "../format";
import type { Threshold } from "../types";
import { btnGhostCls } from "./ui";

interface Point {
  ts: string;
  [k: string]: number | string | null | undefined;
}

/**
 * Single-series time chart (title names the series, so no legend box). Gaps are shown,
 * never filled. Threshold lines are labelled with their level. Includes a table view.
 */
export default function TimeChart({
  points,
  field,
  label,
  stepMs,
  thresholds = [],
  unit = "°C",
  color = "#3a6b7e",
  height = 240,
}: {
  points: Point[];
  field: string;
  label: string;
  stepMs: number;
  thresholds?: Threshold[];
  unit?: string;
  color?: string;
  height?: number;
}) {
  const [asTable, setAsTable] = useState(false);
  const data = withGaps(points, stepMs).map((p) => ({ ...p, t: Date.parse(p.ts) }));
  const fmt = (v: number | null | undefined) => (unit === "°C" ? c(v) : v == null ? "-" : `${v} ${unit}`);

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-ink-2">{label}</span>
        <button className={`${btnGhostCls} text-xs`} onClick={() => setAsTable((v) => !v)}>
          {asTable ? "Lihat grafik" : "Lihat tabel"}
        </button>
      </div>
      {points.length === 0 ? (
        <p className="py-8 text-center text-sm text-ink-3">Belum ada data pada rentang ini.</p>
      ) : asTable ? (
        <div className="max-h-64 overflow-y-auto text-sm">
          <table className="w-full">
            <tbody className="divide-y divide-gray-100">
              {points.map((p) => (
                <tr key={p.ts}>
                  <td className="py-1 text-ink-2">{dt(p.ts)}</td>
                  <td className="py-1 text-right tabular-nums">{fmt(p[field] as number | null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 8, right: 56, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#e5e7eb" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v) => time(v)}
              tick={{ fontSize: 11, fill: "#6b7280" }}
              stroke="#d1d5db"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#6b7280" }}
              stroke="#d1d5db"
              width={40}
              domain={["auto", "auto"]}
              tickFormatter={(v) => `${v}`}
            />
            {thresholds.map((th) => (
              <ReferenceLine
                key={th.id}
                y={th.min_value}
                stroke="#9ca3af"
                strokeDasharray="4 4"
                label={{ value: `${th.level} ${th.min_value}`, position: "right", fontSize: 10, fill: "#4b5563" }}
              />
            ))}
            <Tooltip
              labelFormatter={(v) => dt(new Date(v as number).toISOString())}
              formatter={(v) => [fmt(v as number), label]}
              contentStyle={{ fontSize: 12 }}
            />
            <Line
              dataKey={field}
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: "#fcfcfb" }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
