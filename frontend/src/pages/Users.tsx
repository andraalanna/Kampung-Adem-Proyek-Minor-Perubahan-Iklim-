import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api";
import { btnCls, btnGhostCls, Card, ErrorText, Field, inputCls, Loading, Table } from "../components/ui";
import type { Role } from "../types";

interface UserItem {
  id: number;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  scopes: { district_id: number | null; village_id: number | null; rw_id: number | null }[];
}

const ROLES: Record<Role, string> = {
  admin: "Administrator",
  kelurahan: "Pemerintah kelurahan",
  rtrw: "RT/RW",
  kader: "Kader posyandu",
  teknis: "Tim teknis",
};

export default function Users() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: UserItem[] }>("/users") });
  const [f, setF] = useState({ name: "", email: "", password: "", role: "kelurahan" as Role, scope: "" });
  const create = useMutation({
    mutationFn: () => {
      const ids = f.scope.split(",").map((s) => Number(s.trim())).filter(Boolean);
      return api("/users", {
        method: "POST",
        body: JSON.stringify({
          name: f.name,
          email: f.email,
          password: f.password,
          role: f.role,
          village_ids: f.role === "kelurahan" ? ids : [],
          rw_ids: f.role === "rtrw" || f.role === "kader" ? ids : [],
        }),
      });
    },
    onSuccess: () => {
      setF({ name: "", email: "", password: "", role: "kelurahan", scope: "" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (u: UserItem) => api(`/users/${u.id}?active=${!u.active}`, { method: "PATCH" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Manajemen pengguna</h1>
      <Card title="Tambah pengguna">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nama"><input className={inputCls} required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Email"><input className={inputCls} type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Kata sandi (min. 10)"><input className={inputCls} type="password" required minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <Field label="Peran">
            <select className={inputCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
              {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label={f.role === "kelurahan" ? "ID kelurahan (pisah koma)" : "ID RW (pisah koma)"}>
            <input className={inputCls} disabled={f.role === "admin" || f.role === "teknis"} value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })} />
          </Field>
          <div><button className={btnCls} disabled={create.isPending}>Simpan</button></div>
        </form>
        <ErrorText error={create.error} />
      </Card>
      <Card>
        {q.isLoading ? <Loading /> : (
          <Table head={["Nama", "Email", "Peran", "Cakupan wilayah", "Status", ""]}>
            {q.data?.items.map((u) => (
              <tr key={u.id}>
                <td className="px-2 py-1.5">{u.name}</td>
                <td className="px-2 py-1.5">{u.email}</td>
                <td className="px-2 py-1.5">{ROLES[u.role]}</td>
                <td className="px-2 py-1.5 text-xs">
                  {u.scopes.length === 0 ? "Semua" : u.scopes.map((s) => (s.rw_id ? `RW #${s.rw_id}` : s.village_id ? `Kel. #${s.village_id}` : `Kec. #${s.district_id}`)).join(", ")}
                </td>
                <td className="px-2 py-1.5 text-xs">{u.active ? "Aktif" : "Nonaktif"}</td>
                <td className="px-2 py-1.5">
                  <button className={`${btnGhostCls} text-xs`} onClick={() => toggle.mutate(u)}>{u.active ? "Nonaktifkan" : "Aktifkan"}</button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
