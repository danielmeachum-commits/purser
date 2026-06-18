import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import { formatCurrency, formatDate } from "@/lib/utils";

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

  // On any tx-event, bump pulse so all queries refetch.
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {month ? `${month.start} → ${month.end}` : "loading…"}
          </p>
        </div>
        <Badge variant={connected ? "income" : "outline"}>
          {connected ? "live" : "reconnecting…"}
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Net (this month)" value={month?.net} tone="net" />
        <StatCard label="Inflow (this month)" value={month?.inflow} tone="positive" />
        <StatCard label="Outflow (this month)" value={month?.outflow} tone="negative" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>This year — month over month</CardTitle>
        </CardHeader>
        <CardContent className="h-80">
          {ytdSeries.length === 0 ? (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              No data
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ytdSeries}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="inflow" fill="#10b981" />
                <Bar dataKey="outflow" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By category (this month)</CardTitle>
          </CardHeader>
          <CardContent>
            {month?.groups?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Net</TableHead>
                    <TableHead className="text-right">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {month.groups.map((g) => (
                    <TableRow key={String(g.key)}>
                      <TableCell>{String(g.key)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatCurrency(g.net)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{g.count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-sm text-muted-foreground">No data</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent transactions</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
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
                    <TableCell>{tx.description}</TableCell>
                    <TableCell>{tx.category ?? "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Badge variant={tx.type}>{formatCurrency(tx.amount)}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {txs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                      No transactions yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
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
}

function StatCard({ label, value, tone }: StatProps) {
  const n = value !== undefined ? Number(value) : null;
  const className =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "negative"
        ? "text-red-700"
        : n !== null && n < 0
          ? "text-red-700"
          : "text-emerald-700";
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-3xl font-semibold tabular-nums ${className}`}>
          {value === undefined ? "…" : formatCurrency(value)}
        </div>
      </CardContent>
    </Card>
  );
}
