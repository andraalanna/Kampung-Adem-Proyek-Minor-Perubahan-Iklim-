import type { ReactNode } from "react";
import { STATUS_META } from "../format";
import type { Status } from "../types";

/** Status is always icon + label + color, never color alone. */
export function StatusBadge({ status, estimate = false }: { status: Status; estimate?: boolean }) {
  const m = STATUS_META[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap"
      style={{ background: m.color, color: m.text }}
    >
      <span aria-hidden>{m.icon}</span>
      {m.label}
      {estimate && <span className="font-normal">(perkiraan)</span>}
    </span>
  );
}

export function Card({
  title,
  children,
  actions,
  className = "",
}: {
  title?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-gray-200 bg-surface p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading() {
  return <p className="text-sm text-ink-3">Memuat data...</p>;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p className="text-sm text-red-700">{error instanceof Error ? error.message : "Terjadi kesalahan"}</p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-ink-3">{children}</p>;
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-200 text-xs text-ink-3">
          <tr>
            {head.map((h, i) => (
              <th key={i} className="px-2 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">{children}</tbody>
      </table>
    </div>
  );
}

export const inputCls =
  "w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-brand-teal focus:outline-none";
export const btnCls =
  "rounded bg-brand-teal px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-teal-dark disabled:opacity-50";
export const btnGhostCls = "rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs text-ink-2">{label}</span>
      {children}
    </label>
  );
}

export function SimBanner() {
  return (
    <div className="bg-brand-amber/20 px-4 py-1.5 text-center text-xs text-ink">
      Mode demo: semua data sensor di dashboard ini adalah <strong>data simulasi</strong>, bukan pengukuran
      nyata.
    </div>
  );
}
