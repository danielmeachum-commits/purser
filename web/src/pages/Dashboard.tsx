import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, Scale } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { useEventStream } from "@/lib/ws";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

interface SummaryGroup {
  key: string | Record<string, string>;
  net: string;
  inflow: string;
  outflow: string;
  count: number;
}

interface SummaryBucket {
  period: string;
  net: string;
  inflow: string;
  outflow: string;
  count: number;
}

interface Summary {
  start: string;
  end: string;
  net: string;
  inflow: string;
  outflow: string;
  count: number;
  groups?: SummaryGroup[];
  buckets?: SummaryBucket[];
}

interface Transaction {
  id: number;
  date: string;
  amount: string;
  type: "income" | "expense" | "transfer";
  category: string | null;
  account: string | null;
  description: string;
  is_test: boolean;
  created_at: string;
}

export default function Dashboard() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? undefined;
  const qc = useQueryClient();
  const [pulse, setPulse] = useState(0);

  const monthQ = useQuery({
    queryKey: ["summary-month", token, pulse],
    queryFn: () =>
      api<Summary>("/summary", {
        token,
        query: { date_range: "this month", group_by: "category" },
      }),
  });

  const ytdQ = useQuery({
    queryKey: ["summary-ytd", token, pulse],
    queryFn: () =>
      api<Summary>("/summary", {
        token,
        query: { date_range: "ytd", period: "month", group_by: "none" },
      }),
  });

  const txQ = useQuery({
    queryKey: ["txs", token, pulse],
    queryFn: () =>
      api<Transaction[]>("/transactions", { token, query: { limit: 15 } }),
  });

  const { connected, lastEvent } = useEventStream(token);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type.startsWith("transaction.")) {
      setPulse((p) => p + 1);
      void qc.invalidateQueries();
    }
  }, [lastEvent, qc]);

  const month = monthQ.data;
  const txs = txQ.data ?? [];

  const ytdSeries = useMemo(() => {
    if (!ytdQ.data?.buckets) return [];
    return ytdQ.data.buckets.map((b) => ({
      period: b.period,
      inflow: Number(b.inflow),
      outflow: -Number(b.outflow),
      net: Number(b.net),
    }));
  }, [ytdQ.data]);

  const sortedGroups = useMemo(() => {
    if (!month?.groups) return [];
    return [...month.groups].sort((a, b) => Math.abs(Number(b.net)) - Math.abs(Number(a.net)));
  }, [month?.groups]);

  const dateRangeLabel = month
    ? `${formatDate(month.start)} – ${formatDate(month.end)}`
    : "Loading…";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">{dateRangeLabel}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              connected ? "bg-emerald-500 animate-pulse" : "bg-amber-500",
            )}
          />
          {connected ? "Live" : "Reconnecting…"}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Net" value={month?.net} tone="net" icon={<Scale className="h-4 w-4" />} />
        <StatCard label="Inflow" value={month?.inflow} tone="positive" icon={<ArrowUpRight className="h-4 w-4" />} />
        <StatCard label="Outflow" value={month?.outflow} tone="negative" icon={<ArrowDownLeft className="h-4 w-4" />} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">This year — month over month</CardTitle>
        </CardHeader>
        <CardContent className="h-80">
          {ytdSeries.length === 0 ? (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              No data
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ytdSeries} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={(v) => formatCurrency(Number(v))}
                  contentStyle={{ fontSize: 12, borderRadius: 6 }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="inflow" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="outflow" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base font-semibold">By category (this month)</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sortedGroups.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Net</TableHead>
                    <TableHead className="text-right w-20">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedGroups.map((g) => {
                    const n = Number(g.net);
                    return (
                      <TableRow key={String(g.key)}>
                        <TableCell className="font-medium">{String(g.key)}</TableCell>
                        <TableCell
                          className={cn(
                            "text-right tabular-nums",
                            n < 0 ? "text-red-700" : "text-emerald-700",
                          )}
                        >
                          {formatCurrency(g.net)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {g.count}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            ) : (
              <div className="px-6 py-8 text-center text-sm text-muted-foreground">
                No data this month
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base font-semibold">Recent transactions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {txs.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-muted-foreground">
                No transactions yet
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-24">Date</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {txs.map((tx) => (
                    <TableRow key={tx.id}>
                      <TableCell className="whitespace-nowrap text-muted-foreground">
                        {formatDate(tx.date)}
                      </TableCell>
                      <TableCell className="font-medium">{tx.description}</TableCell>
                      <TableCell className="text-muted-foreground">{tx.category ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        <Badge variant={tx.type}>{formatCurrency(tx.amount)}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface StatProps {
  label: string;
  value: string | undefined;
  tone: "net" | "positive" | "negative";
  icon: React.ReactNode;
}

function StatCard({ label, value, tone, icon }: StatProps) {
  const n = value !== undefined ? Number(value) : null;
  const colorClass =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "negative"
        ? "text-red-700"
        : n !== null && n < 0
          ? "text-red-700"
          : "text-emerald-700";
  const iconBg =
    tone === "positive"
      ? "bg-emerald-500/10 text-emerald-700"
      : tone === "negative"
        ? "bg-red-500/10 text-red-700"
        : "bg-slate-500/10 text-slate-700";

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {label}
            </div>
            <div className={cn("text-3xl font-semibold tabular-nums", colorClass)}>
              {value === undefined ? "…" : formatCurrency(value)}
            </div>
          </div>
          <div className={cn("rounded-md p-2", iconBg)}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}
