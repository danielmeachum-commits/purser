import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  CreditCard,
  Folder,
  ListOrdered,
  Tags,
  KeyRound,
  LogOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/admin/transactions", label: "Transactions", icon: ListOrdered },
  { to: "/admin/accounts", label: "Accounts", icon: CreditCard },
  { to: "/admin/categories", label: "Categories", icon: Folder },
  { to: "/admin/types", label: "Account types", icon: Tags },
  { to: "/admin/tokens", label: "Service tokens", icon: KeyRound },
];

export default function AdminShell({ children }: { children: ReactNode }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen flex bg-muted/30">
      <aside className="w-60 border-r bg-background flex flex-col sticky top-0 h-screen">
        <div className="px-6 py-5 border-b">
          <div className="font-semibold tracking-tight">budget-graph</div>
          <div className="text-xs text-muted-foreground">admin</div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/dashboard"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="p-3 border-t">
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            Sign out
          </Button>
        </div>
      </aside>
      <main className="flex-1 min-w-0 p-8 overflow-x-auto">{children}</main>
    </div>
  );
}
