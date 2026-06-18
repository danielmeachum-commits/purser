import { Outlet } from "react-router-dom";
import AdminShell from "./AdminShell";

export default function Layout() {
  return (
    <AdminShell>
      <Outlet />
    </AdminShell>
  );
}
