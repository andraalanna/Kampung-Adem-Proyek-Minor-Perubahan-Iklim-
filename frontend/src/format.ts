import type { Status } from "./types";

export const STATUS_META: Record<Status, { label: string; color: string; icon: string; text: string }> = {
  NORMAL: { label: "Normal", color: "#0ca30c", icon: "✓", text: "#ffffff" },
  WASPADA: { label: "Waspada", color: "#fab219", icon: "!", text: "#1f2328" },
  SIAGA: { label: "Siaga", color: "#ec835a", icon: "▲", text: "#1f2328" },
  AWAS: { label: "Awas", color: "#d03b3b", icon: "◆", text: "#ffffff" },
  TIDAK_ADA_DATA: { label: "Tidak ada data", color: "#9ca3af", icon: "?", text: "#1f2328" },
};

export const STATUS_ORDER: Status[] = ["AWAS", "SIAGA", "WASPADA", "NORMAL", "TIDAK_ADA_DATA"];

// One-hue orange ramp for LST (land surface temperature) magnitude, light -> dark.
export const LST_RAMP = ["#fde3cf", "#f9bd8f", "#f29150", "#d9661f", "#a8470f"];
export const LST_BREAKS = [30, 35, 40, 45]; // degrees C, upper bounds of the first 4 steps

export function lstColor(v: number | null | undefined): string {
  if (v == null) return "#e5e7eb";
  const i = LST_BREAKS.findIndex((b) => v < b);
  return LST_RAMP[i === -1 ? LST_RAMP.length - 1 : i];
}

const nf1 = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

export function c(v: number | null | undefined): string {
  return v == null ? "-" : `${nf1.format(v)} °C`;
}

export function pct(v: number | null | undefined): string {
  return v == null ? "-" : `${nf0.format(v)} %`;
}

const dtf = new Intl.DateTimeFormat("id-ID", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Jakarta",
});
const tf = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" });
const df = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Jakarta" });

export function dt(iso: string | null | undefined): string {
  return iso ? `${dtf.format(new Date(iso))} WIB` : "-";
}

export function time(iso: string | number): string {
  return tf.format(new Date(iso));
}

export function date(iso: string | null | undefined): string {
  return iso ? df.format(new Date(iso)) : "-";
}

/**
 * Insert null points where consecutive timestamps are further apart than `stepMs`, so charts
 * show a gap instead of drawing a line across missing data (missing data is never filled).
 */
export function withGaps<T extends { ts: string }>(points: T[], stepMs: number): (T | { ts: string })[] {
  const out: (T | { ts: string })[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i > 0) {
      const prev = Date.parse(points[i - 1].ts);
      const cur = Date.parse(points[i].ts);
      if (cur - prev > stepMs * 1.5) out.push({ ts: new Date(prev + stepMs).toISOString() });
    }
    out.push(points[i]);
  }
  return out;
}
