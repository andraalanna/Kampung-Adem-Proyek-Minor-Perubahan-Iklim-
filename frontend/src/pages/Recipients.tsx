import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { btnCls, btnGhostCls, Card, ErrorText, Field, inputCls, Loading, Table } from "../components/ui";
import { dt } from "../format";
import type { RecipientItem } from "../types";

interface RwOpt {
  id: number;
  name: string;
  village_name: string;
}

const ROLE: Record<string, string> = {
  ketua_rw: "Ketua RW",
  ketua_rt: "Ketua RT",
  kader: "Kader posyandu",
  staf_kelurahan: "Staf kelurahan",
};

export default function Recipients() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["recipients"], queryFn: () => api<{ items: RecipientItem[] }>("/recipients") });
  const rws = useQuery({ queryKey: ["regions", "rw"], queryFn: () => api<{ items: RwOpt[] }>("/regions?level=rw") });
  const rwName = (id: number) => {
    const r = rws.data?.items.find((x) => x.id === id);
    return r ? `${r.name}, ${r.village_name}` : `RW #${id}`;
  };

  const [form, setForm] = useState({ rw_id: "", name: "", role: "kader", phone: "", opt_in: false, evidence: "" });
  const create = useMutation({
    mutationFn: () =>
      api("/recipients", {
        method: "POST",
        body: JSON.stringify({
          rw_id: Number(form.rw_id),
          name: form.name,
          role: form.role,
          phone: form.phone,
          opt_in_at: form.opt_in ? new Date().toISOString() : null,
          opt_in_evidence: form.evidence || null,
        }),
      }),
    onSuccess: () => {
      setForm({ rw_id: form.rw_id, name: "", role: "kader", phone: "", opt_in: false, evidence: "" });
      qc.invalidateQueries({ queryKey: ["recipients"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (r: RecipientItem) => api(`/recipients/${r.id}`, { method: "PATCH", body: JSON.stringify({ active: !r.active }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recipients"] }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Penerima WhatsApp</h1>
      <Card title="Tambah penerima">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="RW">
            <select className={inputCls} required value={form.rw_id} onChange={(e) => setForm({ ...form, rw_id: e.target.value })}>
              <option value="">Pilih RW</option>
              {rws.data?.items.map((r) => (
                <option key={r.id} value={r.id}>{r.name}, {r.village_name}</option>
              ))}
            </select>
          </Field>
          <Field label="Nama">
            <input className={inputCls} required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Peran">
            <select className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {Object.entries(ROLE).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </Field>
          <Field label="Nomor HP">
            <input className={inputCls} required placeholder="08xx" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input type="checkbox" checked={form.opt_in} onChange={(e) => setForm({ ...form, opt_in: e.target.checked })} />
            Penerima sudah menyetujui secara tertulis menerima pesan Kampung Adem (opt-in)
          </label>
          <Field label="Bukti opt-in (mis. nomor formulir)">
            <input className={inputCls} value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
          </Field>
          <div className="flex items-end">
            <button className={btnCls} disabled={create.isPending}>Simpan</button>
          </div>
        </form>
        <p className="mt-2 text-xs text-ink-3">
          Tanpa opt-in, penerima tersimpan tetapi tidak akan menerima pesan. Nomor disimpan terenkripsi dan hanya ditampilkan tersamar.
        </p>
        <ErrorText error={create.error} />
      </Card>

      <Card>
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <ErrorText error={q.error} />
        ) : (
          <Table head={["Nama", "Peran", "RW", "Nomor", "Opt-in", "Status", ""]}>
            {q.data!.items.map((r) => (
              <tr key={r.id}>
                <td className="px-2 py-1.5">{r.name}</td>
                <td className="px-2 py-1.5">{ROLE[r.role] ?? r.role}</td>
                <td className="px-2 py-1.5">{rwName(r.rw_id)}</td>
                <td className="px-2 py-1.5 font-mono text-xs">{r.phone_masked}</td>
                <td className="px-2 py-1.5 text-xs">{r.opt_in_at ? dt(r.opt_in_at) : "Belum"}</td>
                <td className="px-2 py-1.5 text-xs">
                  {r.opt_out_at ? `Berhenti (STOP) ${dt(r.opt_out_at)}` : r.active ? "Aktif" : "Nonaktif"}
                  {r.last_failure && <div className="text-red-700">Gagal: {r.last_failure}</div>}
                </td>
                <td className="px-2 py-1.5">
                  {!r.opt_out_at && (
                    <button className={`${btnGhostCls} text-xs`} onClick={() => toggle.mutate(r)}>
                      {r.active ? "Nonaktifkan" : "Aktifkan"}
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
