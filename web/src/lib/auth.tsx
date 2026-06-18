import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";

interface WhoAmI {
  authenticated: boolean;
  scope?: "admin" | "read" | null;
  source?: "session" | "token" | null;
}

interface AuthState extends WhoAmI {
  loading: boolean;
  login: (password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WhoAmI>({ authenticated: false });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api<WhoAmI>("/auth/me");
      setState(me);
    } catch {
      setState({ authenticated: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (password: string) => {
      await api<void>("/auth/login", { method: "POST", body: { password } });
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await api<void>("/auth/logout", { method: "POST" });
    setState({ authenticated: false });
  }, []);

  const value = useMemo(
    () => ({ ...state, loading, login, logout, refresh }),
    [state, loading, login, logout, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth used outside AuthProvider");
  return v;
}
