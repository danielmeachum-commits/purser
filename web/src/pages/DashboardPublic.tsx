// Dashboard route that works for both admin sessions and ?token=... callers.
// We don't gate it behind <Protected> because read-only tokens authenticate
// via the query param instead of a cookie. Admins get the sidebar shell;
// token visitors get the bare dashboard for wall displays.
import { Link, useSearchParams } from "react-router-dom";
import AdminShell from "@/components/AdminShell";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import Dashboard from "./Dashboard";

export default function DashboardPublic() {
  const [params] = useSearchParams();
  const hasToken = !!params.get("token");
  const { loading, authenticated } = useAuth();

  if (!hasToken) {
    if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
    if (!authenticated) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-6 text-center">
          <h1 className="text-xl font-semibold">Sign in or use a token</h1>
          <p className="text-sm text-muted-foreground max-w-sm">
            Admin sessions sign in with a password. Wall displays open the dashboard with a
            <code className="mx-1 rounded bg-muted px-1.5 py-0.5 text-xs">?token=…</code>
            URL generated from the Service tokens page.
          </p>
          <Button asChild>
            <Link to="/login">Sign in</Link>
          </Button>
        </div>
      );
    }
    return (
      <AdminShell>
        <Dashboard />
      </AdminShell>
    );
  }

  return (
    <div className="min-h-screen bg-muted/30 p-8">
      <Dashboard />
    </div>
  );
}
