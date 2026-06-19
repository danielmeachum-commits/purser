import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, ChevronRight, PiggyBank, Scale } from "lucide-react";
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
  buckets?: SummaryBucket[];
}

interface CategoryRow {
  id: number;
  name: string;
  type: "income" | "expense" | "transfer";
  parent_id: number | null;
  monthly_budget: string | null;
  target_amount: string | null;
  direct_net: string;
  direct_count: number;
}

interface CategoryBreakdown {
  start: string;
  end: string;
  categories: CategoryRow[];
}

interface SavingsGoal {
  id: number;
  name: string;
  target_amount: string;
  allocated_amount: string;
  account: string | null;
  notes: string | null;
  is_active: boolean;
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

interface CatNode extends CategoryRow {
  directNet: number;
  rollupNet: number;
  rollupCount: number;
  budget: number | null;
  children: CatNode[];
}

function buildTree(rows: CategoryRow[]): CatNode[] {
  const byId = new Map<number, CatNode>();
  for (const r of rows) {
    byId.set(r.id, {
      ...r,
      directNet: Number(r.direct_net),
      rollupNet: 0,
      rollupCount: r.direct_count,
      budget: r.monthly_budget !== null ? Number(r.monthly_budget) : null,
      children: [],
    });
  }
  const roots: CatNode[] = [];
  for (const node of byId.values()) {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const computeRollup = (node: CatNode): void => {
    let net = node.directNet;
    let count = node.direct_count;
    for (const child of node.children) {
      computeRollup(child);
      net += child.rollupNet;
      count += child.rollupCount;
    }
    node.rollupNet = net;
    node.rollupCount = count;
    node.children.sort((a, b) => Math.abs(b.rollupNet) - Math.abs(a.rollupNet));
  };
  for (const root of roots) computeRollup(root);
  roots.sort((a, b) => {
    if (a.type !== b.type) {
      const order = { expense: 0, income: 1, transfer: 2 } as const;
      return order[a.type] - order[b.type];
    }
    return Math.abs(b.rollupNet) - Math.abs(a.rollupNet);
  });
  return roots;
}

export default function Dashboard() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? undefined;
  const qc = useQueryClient();
  const [pulse, setPulse] = useState(0);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const monthQ = useQuery({
    queryKey: ["summary-month", token, pulse],
    queryFn: () =>
      api<Summary>("/summary", {
        token,
        query: { date_range: "this month", group_by: "none" },
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

  const breakdownQ = useQuery({
    queryKey: ["summary-categories", token, pulse],
    queryFn: () =>
      api<CategoryBreakdown>("/summary/categories", {
        token,
        query: { date_range: "this month" },
      }),
  });

  const savingsQ = useQuery({
    queryKey: ["savings-goals", token, pulse],
    queryFn: () =>
      api<SavingsGoal[]>("/savings-goals", { token }),
  });

  const txQ = useQuery({
    queryKey: ["txs", token, pulse],
    queryFn: () =>
      api<Transaction[]>("/transactions", { token, query: { limit: 15 } }),
  });

  const { connected, lastEvent } = useEventStream(token);

  useEffect(() => {
    if (!lastEvent) return;
    if (
      lastEvent.type.startsWith("transaction.") ||
      lastEvent.type.startsWith("category.") ||
      lastEvent.type.startsWith("savings_goal.")
    ) {
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

  const tree = useMemo(
    () => buildTree(breakdownQ.data?.categories ?? []),
    [breakdownQ.data],
  );

  const expenseRoots = useMemo(
    () => tree.filter((n) => n.type === "expense"),
    [tree],
  );

  const budgetSeries = useMemo(() => {
    return expenseRoots
      .filter((n) => n.budget !== null && n.budget > 0)
      .map((n) => ({
        name: n.name,
        spent: Math.abs(n.rollupNet),
        budget: n.budget ?? 0,
        pct: (n.budget ?? 0) > 0 ? Math.abs(n.rollupNet) / (n.budget ?? 1) : 0,
      }));
  }, [expenseRoots]);

  const savingsGoals = savingsQ.data ?? [];

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

      <BudgetCard rows={budgetSeries} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base font-semibold">By category (this month)</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {tree.length ? (
              <CategoryTree
                roots={tree}
                expanded={expanded}
                onToggle={(id) => setExpanded((s) => ({ ...s, [id]: !s[id] }))}
              />
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

      <SavingsCard goals={savingsGoals} />
    </div>
  );
}

function CategoryTree({
  roots,
  expanded,
  onToggle,
}: {
  roots: CatNode[];
  expanded: Record<number, boolean>;
  onToggle: (id: number) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Category</TableHead>
          <TableHead className="text-right">Total</TableHead>
          <TableHead className="text-right w-20">Count</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {roots.flatMap((node) => renderNode(node, 0, expanded, onToggle))}
      </TableBody>
    </Table>
  );
}

function renderNode(
  node: CatNode,
  depth: number,
  expanded: Record<number, boolean>,
  onToggle: (id: number) => void,
): React.ReactNode[] {
  const hasChildren = node.children.length > 0;
  const isOpen = expanded[node.id] ?? true;
  const total = node.rollupNet;
  const direct = node.directNet;
  const showSplit = hasChildren && direct !== 0 && direct !== total;

  const rows: React.ReactNode[] = [
    <TableRow key={node.id}>
      <TableCell className="font-medium" style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
        <div className="flex items-center gap-1.5">
          {hasChildren ? (
            <button
              type="button"
              onClick={() => onToggle(node.id)}
              className="text-muted-foreground hover:text-foreground transition-transform"
              aria-label={isOpen ? "Collapse" : "Expand"}
            >
              <ChevronRight
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  isOpen && "rotate-90",
                )}
              />
            </button>
          ) : (
            <span className="inline-block w-3.5" />
          )}
          <span>{node.name}</span>
        </div>
      </TableCell>
      <TableCell
        className={cn(
          "text-right tabular-nums",
          total < 0 ? "text-red-700" : total > 0 ? "text-emerald-700" : "text-muted-foreground",
        )}
      >
        <div className="flex flex-col items-end">
          <span>{formatCurrency(total)}</span>
          {showSplit && (
            <span className="text-[10px] font-normal text-muted-foreground">
              own {formatCurrency(direct)}
            </span>
          )}
        </div>
      </TableCell>
      <TableCell className="text-right tabular-nums text-muted-foreground">
        {node.rollupCount}
      </TableCell>
    </TableRow>,
  ];

  if (hasChildren && isOpen) {
    for (const child of node.children) {
      rows.push(...renderNode(child, depth + 1, expanded, onToggle));
    }
  }
  return rows;
}

function BudgetCard({ rows }: { rows: { name: string; spent: number; budget: number; pct: number }[] }) {
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Budgets vs. actuals</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">
            No category budgets set yet. Add a monthly budget on any expense category to see it here.
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">Budgets vs. actuals (this month)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {rows.map((r) => {
            const pctClamped = Math.min(1.4, r.pct);
            const over = r.pct > 1;
            const overshoot = r.pct > 1 ? Math.min(0.4, r.pct - 1) : 0;
            return (
              <div key={r.name} className="space-y-1">
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-medium">{r.name}</span>
                  <span className="tabular-nums text-muted-foreground">
                    <span className={cn(over && "text-red-700 font-medium")}>
                      {formatCurrency(r.spent)}
                    </span>
                    <span> / {formatCurrency(r.budget)}</span>
                    <span className="ml-2 text-xs">
                      {Math.round(r.pct * 100)}%
                    </span>
                  </span>
                </div>
                <div className="h-2 w-full rounded bg-muted overflow-hidden flex">
                  <div
                    className={cn(
                      "h-full transition-all",
                      over ? "bg-red-500" : r.pct > 0.85 ? "bg-amber-500" : "bg-emerald-500",
                    )}
                    style={{ width: `${Math.min(1, pctClamped) * 100}%` }}
                  />
                  {overshoot > 0 && (
                    <div
                      className="h-full bg-red-700"
                      style={{ width: `${overshoot * 100}%` }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function SavingsCard({ goals }: { goals: SavingsGoal[] }) {
  if (goals.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <PiggyBank className="h-4 w-4 text-sky-600" /> Savings goals
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-2">
          {goals.map((g) => {
            const target = Number(g.target_amount);
            const allocated = Number(g.allocated_amount);
            const pct = target > 0 ? Math.min(1, allocated / target) : 0;
            const done = pct >= 1;
            return (
              <div key={g.id} className="space-y-2 rounded-md border p-3">
                <div className="flex items-baseline justify-between">
                  <div className="font-medium">{g.name}</div>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {formatCurrency(allocated)} / {formatCurrency(target)}
                  </div>
                </div>
                <div className="h-2 w-full rounded bg-muted overflow-hidden">
                  <div
                    className={cn(
                      "h-full transition-all",
                      done ? "bg-emerald-500" : "bg-sky-500",
                    )}
                    style={{ width: `${Math.max(2, pct * 100)}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{Math.round(pct * 100)}%</span>
                  {g.account && <span>{g.account}</span>}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
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
