import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";

interface Props {
  children: ReactNode;
  requireAdmin?: boolean;
}

export default function Protected({ children, requireAdmin = false }: Props) {
  const { loading, authenticated, scope } = useAuth();
  if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  if (!authenticated) return <Navigate to="/login" replace />;
  if (requireAdmin && scope !== "admin") return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
