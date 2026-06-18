import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/lib/auth";
import Layout from "@/components/Layout";
import Protected from "@/components/Protected";
import Dashboard from "@/pages/Dashboard";
import Login from "@/pages/Login";
import Transactions from "@/pages/Transactions";
import Accounts from "@/pages/Accounts";
import Categories from "@/pages/Categories";
import Types from "@/pages/Types";
import Tokens from "@/pages/Tokens";
import Chat from "@/pages/Chat";
import DashboardPublic from "@/pages/DashboardPublic";

const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<DashboardPublic />} />
          <Route
            element={
              <Protected requireAdmin>
                <Layout />
              </Protected>
            }
          >
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/admin/chat" element={<Chat />} />
            <Route path="/admin/transactions" element={<Transactions />} />
            <Route path="/admin/accounts" element={<Accounts />} />
            <Route path="/admin/categories" element={<Categories />} />
            <Route path="/admin/types" element={<Types />} />
            <Route path="/admin/tokens" element={<Tokens />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  );
}
