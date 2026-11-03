import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, login as apiLogin, logout as apiLogout, tryRestoreSession } from "./api";
import type { Me, Role } from "./types";

interface AuthCtx {
  me: Me | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [restored, setRestored] = useState<boolean | null>(null);

  useEffect(() => {
    tryRestoreSession().then(setRestored);
  }, []);

  const meQ = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/auth/me"),
    enabled: restored === true,
    retry: false,
  });

  const value: AuthCtx = {
    me: meQ.data ?? null,
    ready: restored === false || (restored === true && !meQ.isLoading),
    login: async (email, password) => {
      await apiLogin(email, password);
      setRestored(true);
      await qc.invalidateQueries({ queryKey: ["me"] });
    },
    logout: async () => {
      await apiLogout();
      qc.clear();
      setRestored(false);
    },
    can: (...roles) => !!meQ.data && roles.includes(meQ.data.role),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
