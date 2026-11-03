import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import type { Role } from "../types";
import { SimBanner } from "./ui";

const NAV: { to: string; label: string; roles?: Role[] }[] = [
  { to: "/", label: "Dashboard" },
  { to: "/peta", label: "Peta panas" },
  { to: "/peringatan", label: "Peringatan" },
  { to: "/sensor", label: "Sensor", roles: ["admin", "kelurahan", "teknis"] },
  { to: "/penerima", label: "Penerima WA", roles: ["admin", "kelurahan"] },
  { to: "/ambang", label: "Ambang" },
  { to: "/laporan", label: "Laporan", roles: ["admin", "kelurahan", "teknis"] },
  { to: "/pengguna", label: "Pengguna", roles: ["admin"] },
];

const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  kelurahan: "Kelurahan",
  rtrw: "RT/RW",
  kader: "Kader",
  teknis: "Tim teknis",
};

export default function Layout() {
  const { me, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="bg-brand-teal text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="rounded bg-white p-0.5">
              <img src="/logo.svg" alt="" className="h-8 w-9" />
            </span>
            <span className="text-lg font-semibold">Kampung Adem</span>
          </NavLink>
          <nav className="flex flex-1 flex-wrap gap-1 text-sm">
            {NAV.filter((n) => !n.roles || (me && n.roles.includes(me.role))).map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `rounded px-2.5 py-1 ${isActive ? "bg-white/20 font-medium" : "hover:bg-white/10"}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          {me && (
            <div className="flex items-center gap-3 text-sm">
              <span>
                {me.name} <span className="text-white/70">({ROLE_LABEL[me.role]})</span>
              </span>
              <button onClick={logout} className="rounded border border-white/40 px-2 py-0.5 hover:bg-white/10">
                Keluar
              </button>
            </div>
          )}
        </div>
      </header>
      <SimBanner />
      <main className="mx-auto max-w-7xl p-4">
        <Outlet />
      </main>
    </div>
  );
}
