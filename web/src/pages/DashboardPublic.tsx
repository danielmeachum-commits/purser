// Dashboard route that works for both admin sessions and ?token=... callers.
// We don't gate it behind <Protected> because read-only tokens authenticate
// via the query param instead of a cookie.
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import Dashboard from "./Dashboard";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

export default function DashboardPublic() {
  const [params] = useSearchParams();
  const hasToken = params.get("token");
  const { loading, authenticated } = useAuth();

  if (!hasToken) {
    if (loading) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
    if (!authenticated) {
      return (
        <div className="min-h-screen flex flex-col items-center justify-center gap-4">
          <h1 className="text-xl font-semibold">Sign in or use a token</h1>
          <p className="text-sm text-muted-foreground">
            Admin sessions: sign in. Wall displays: open with ?token=…
          </p>
          <Button asChild>
            <Link to="/login">Sign in</Link>
          </Button>
        </div>
      );
    }
  }

  return (
    <div className="min-h-screen bg-muted/30 p-8">
      <Dashboard />
    </div>
  );
}
