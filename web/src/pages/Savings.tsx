import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PiggyBank, Pencil, Plus, Trash2 } from "lucide-react";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { SortableHeader } from "@/components/ui/sortable-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useTableSort } from "@/lib/useTableSort";
import { cn, formatCurrency } from "@/lib/utils";

interface SavingsGoal {
  id: number;
  name: string;
  target_amount: string;
  allocated_amount: string;
  account: string | null;
  notes: string | null;
  is_active: boolean;
}

interface Account {
  id: number;
  nickname: string;
}

export default function Savings() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SavingsGoal | null>(null);

  const goalsQ = useQuery({
    queryKey: ["savings-goals"],
    queryFn: () =>
      api<SavingsGoal[]>("/savings-goals", { query: { include_inactive: true } }),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts-all"],
    queryFn: () => api<Account[]>("/accounts", { query: { include_inactive: true } }),
  });

  const { sorted: rows, sort, toggle } = useTableSort<
    SavingsGoal,
    "name" | "progress" | "target" | "account" | "status"
  >(goalsQ.data ?? [], {
    storageKey: "budget.sort.savings",
    columns: {
      name: { accessor: (g) => g.name },
      progress: {
        accessor: (g) =>
          Number(g.target_amount) > 0
            ? Number(g.allocated_amount) / Number(g.target_amount)
            : 0,
      },
      target: { accessor: (g) => Number(g.target_amount) },
      account: { accessor: (g) => g.account },
      status: { accessor: (g) => (g.is_active ? "active" : "inactive") },
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Savings goals"
        description="Named targets with manually-tracked allocations. Useful for tracking sinking funds or savings buckets that don't map to a single account."
        actions={
          <Dialog open={creating} onOpenChange={setCreating}>
            <DialogTrigger asChild>
              <Button><Plus className="h-4 w-4 mr-2" /> New goal</Button>
            </DialogTrigger>
            <DialogContent>
              <GoalForm
                accounts={accountsQ.data ?? []}
                onDone={() => {
                  setCreating(false);
                  qc.invalidateQueries({ queryKey: ["savings-goals"] });
                }}
              />
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState
            icon={<PiggyBank className="h-5 w-5" />}
            title="No savings goals yet"
            description="Create a goal like “Emergency fund” to track progress."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader sortKey="name" sort={sort} onToggle={toggle}>
                  Name
                </SortableHeader>
                <SortableHeader sortKey="progress" sort={sort} onToggle={toggle}>
                  Progress
                </SortableHeader>
                <SortableHeader className="w-32 text-right" sortKey="target" sort={sort} onToggle={toggle}>
                  Target
                </SortableHeader>
                <SortableHeader sortKey="account" sort={sort} onToggle={toggle}>
                  Account
                </SortableHeader>
                <SortableHeader className="w-24" sortKey="status" sort={sort} onToggle={toggle}>
                  Status
                </SortableHeader>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((g) => {
                const target = Number(g.target_amount);
                const allocated = Number(g.allocated_amount);
                const pct = target > 0 ? Math.min(1, allocated / target) : 0;
                return (
                  <TableRow key={g.id}>
                    <TableCell className="font-medium">{g.name}</TableCell>
                    <TableCell>
                      <div className="space-y-1 min-w-[180px]">
                        <div className="flex items-center justify-between text-xs text-muted-foreground tabular-nums">
                          <span>{formatCurrency(allocated)}</span>
                          <span>{Math.round(pct * 100)}%</span>
                        </div>
                        <div className="h-2 w-full rounded bg-muted overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded transition-all",
                              pct >= 1 ? "bg-emerald-500" : "bg-sky-500",
                            )}
                            style={{ width: `${Math.max(2, pct * 100)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatCurrency(target)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{g.account ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={g.is_active ? "income" : "outline"}>
                        {g.is_active ? "active" : "inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end">
                        <Button size="icon" variant="ghost" onClick={() => setEditing(g)} aria-label="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          {editing && (
            <GoalForm
              goal={editing}
              accounts={accountsQ.data ?? []}
              onDone={() => {
                setEditing(null);
                qc.invalidateQueries({ queryKey: ["savings-goals"] });
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GoalForm({
  goal,
  accounts,
  onDone,
}: {
  goal?: SavingsGoal;
  accounts: Account[];
  onDone: () => void;
}) {
  const isEdit = !!goal;
  const [name, setName] = useState(goal?.name ?? "");
  const [targetAmount, setTargetAmount] = useState(goal?.target_amount ?? "");
  const [allocatedAmount, setAllocatedAmount] = useState(goal?.allocated_amount ?? "0");
  const [account, setAccount] = useState(goal?.account ?? "");
  const [notes, setNotes] = useState(goal?.notes ?? "");
  const [isActive, setIsActive] = useState(goal?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const accountOptions = useMemo(
    () => [...accounts].sort((a, b) => a.nickname.localeCompare(b.nickname)),
    [accounts],
  );

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        name,
        target_amount: targetAmount,
        allocated_amount: allocatedAmount || "0",
        account: account === "" ? (isEdit ? "" : null) : account,
        notes: notes || null,
      };
      if (isEdit) body.is_active = isActive;
      if (isEdit) {
        return api(`/savings-goals/${goal!.id}`, { method: "PATCH", body });
      }
      return api("/savings-goals", { method: "POST", body });
    },
    onSuccess: onDone,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "failed"),
  });

  const del = useMutation({
    mutationFn: () => api(`/savings-goals/${goal!.id}`, { method: "DELETE" }),
    onSuccess: onDone,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "failed"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    save.mutate();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{isEdit ? "Edit savings goal" : "New savings goal"}</DialogTitle>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2 col-span-2">
          <Label>Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Emergency fund"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Target amount</Label>
          <Input
            value={targetAmount}
            onChange={(e) => setTargetAmount(e.target.value)}
            placeholder="e.g. 10000"
            inputMode="decimal"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Allocated so far</Label>
          <Input
            value={allocatedAmount}
            onChange={(e) => setAllocatedAmount(e.target.value)}
            placeholder="e.g. 2500"
            inputMode="decimal"
          />
        </div>
        <div className="space-y-2 col-span-2">
          <Label>Account (optional)</Label>
          <Select value={account || "__none__"} onValueChange={(v) => setAccount(v === "__none__" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="(none)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(none)</SelectItem>
              {accountOptions.map((a) => (
                <SelectItem key={a.id} value={a.nickname}>{a.nickname}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2 col-span-2">
          <Label>Notes (optional)</Label>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Any context to remember"
          />
        </div>
        {isEdit && (
          <div className="col-span-2 flex items-center gap-2 pt-1">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="goal-active" />
            <Label htmlFor="goal-active" className="cursor-pointer">
              Active
            </Label>
          </div>
        )}
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter className="flex justify-between">
        {isEdit ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive"
            onClick={() => {
              if (confirm(`Delete savings goal "${goal!.name}"?`)) del.mutate();
            }}
            disabled={del.isPending}
          >
            <Trash2 className="h-4 w-4 mr-2" /> Delete
          </Button>
        ) : <span />}
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : isEdit ? "Save changes" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}
