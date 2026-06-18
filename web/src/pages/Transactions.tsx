import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListOrdered, Pencil, Plus, Search, Trash2 } from "lucide-react";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { api } from "@/lib/api";
import { useTableSort } from "@/lib/useTableSort";
import { formatCurrency, formatDate } from "@/lib/utils";

interface Tx {
  id: number;
  date: string;
  amount: string;
  type: "income" | "expense" | "transfer";
  category: string | null;
  account: string | null;
  description: string;
  is_test: boolean;
}

interface Cat { id: number; name: string; type: string }
interface Acct { id: number; nickname: string }

export default function Transactions() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Tx | null>(null);
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState("");

  const txQ = useQuery({ queryKey: ["txs"], queryFn: () => api<Tx[]>("/transactions", { query: { limit: 200, test_mode: "include" } }) });
  const catsQ = useQuery({ queryKey: ["cats"], queryFn: () => api<Cat[]>("/categories") });
  const acctsQ = useQuery({ queryKey: ["accts"], queryFn: () => api<Acct[]>("/accounts") });

  const del = useMutation({
    mutationFn: (id: number) => api<void>(`/transactions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["txs"] }),
  });

  const filtered = useMemo(() => {
    const all = txQ.data ?? [];
    if (!filter.trim()) return all;
    const q = filter.toLowerCase();
    return all.filter(
      (tx) =>
        tx.description.toLowerCase().includes(q) ||
        (tx.category ?? "").toLowerCase().includes(q) ||
        (tx.account ?? "").toLowerCase().includes(q),
    );
  }, [txQ.data, filter]);

  const { sorted: rows, sort, toggle } = useTableSort<Tx, "date" | "description" | "type" | "category" | "account" | "amount">(
    filtered,
    {
      storageKey: "budget.sort.transactions",
      initial: { key: "date", direction: "desc" },
      columns: {
        date: { accessor: (t) => t.date, type: "date" },
        description: { accessor: (t) => t.description },
        type: { accessor: (t) => t.type },
        category: { accessor: (t) => t.category },
        account: { accessor: (t) => t.account },
        amount: { accessor: (t) => t.amount, type: "number" },
      },
    },
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Transactions"
        description="Every income, expense, and transfer recorded across your accounts."
        actions={
          <Dialog open={creating} onOpenChange={setCreating}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" /> New
              </Button>
            </DialogTrigger>
            <DialogContent>
              <TxForm
                categories={catsQ.data ?? []}
                accounts={acctsQ.data ?? []}
                onDone={() => {
                  setCreating(false);
                  qc.invalidateQueries({ queryKey: ["txs"] });
                }}
              />
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between gap-4 border-b px-4 py-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by description, category, or account…"
              className="pl-8"
            />
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">
            {rows.length}
            {rows.length !== (txQ.data?.length ?? 0) && ` of ${txQ.data?.length ?? 0}`}
            {rows.length === 1 ? " row" : " rows"}
          </div>
        </div>

        {rows.length === 0 ? (
          <EmptyState
            icon={<ListOrdered className="h-5 w-5" />}
            title={filter ? "No matches" : "No transactions yet"}
            description={
              filter
                ? "Try a different filter."
                : "Click “New” to record one, or log it via the LangGraph agent."
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader className="w-28" sortKey="date" sort={sort} onToggle={toggle}>
                  Date
                </SortableHeader>
                <SortableHeader sortKey="description" sort={sort} onToggle={toggle}>
                  Description
                </SortableHeader>
                <SortableHeader sortKey="type" sort={sort} onToggle={toggle}>
                  Type
                </SortableHeader>
                <SortableHeader sortKey="category" sort={sort} onToggle={toggle}>
                  Category
                </SortableHeader>
                <SortableHeader sortKey="account" sort={sort} onToggle={toggle}>
                  Account
                </SortableHeader>
                <SortableHeader sortKey="amount" sort={sort} onToggle={toggle} align="right">
                  Amount
                </SortableHeader>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {formatDate(tx.date)}
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{tx.description}</span>
                    {tx.is_test && (
                      <Badge variant="outline" className="ml-2">
                        test
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={tx.type}>{tx.type}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {tx.category ?? "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {tx.account ?? "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {formatCurrency(tx.amount)}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => setEditing(tx)}
                        aria-label="Edit"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => {
                          if (confirm(`Delete transaction "${tx.description}"?`)) del.mutate(tx.id);
                        }}
                        aria-label="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          {editing && (
            <TxForm
              tx={editing}
              categories={catsQ.data ?? []}
              accounts={acctsQ.data ?? []}
              onDone={() => {
                setEditing(null);
                qc.invalidateQueries({ queryKey: ["txs"] });
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface FormProps {
  tx?: Tx;
  categories: Cat[];
  accounts: Acct[];
  onDone: () => void;
}

function TxForm({ tx, categories, accounts, onDone }: FormProps) {
  const isEdit = !!tx;
  const [type, setType] = useState<"income" | "expense" | "transfer">(tx?.type ?? "expense");
  const [amount, setAmount] = useState(tx?.amount ?? "");
  const [description, setDescription] = useState(tx?.description ?? "");
  const [date, setDate] = useState(tx?.date ?? new Date().toISOString().slice(0, 10));
  const [category, setCategory] = useState(tx?.category ?? "");
  const [account, setAccount] = useState(tx?.account ?? "");
  const [isTest, setIsTest] = useState(tx?.is_test ?? false);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        type,
        amount,
        description,
        date,
        category: category || null,
        account: account || null,
        is_test: isTest,
      };
      if (isEdit) return api(`/transactions/${tx!.id}`, { method: "PATCH", body });
      return api("/transactions", { method: "POST", body });
    },
    onSuccess: () => onDone(),
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "failed"),
  });

  const filteredCats = categories.filter((c) => c.type === type);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    save.mutate();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{isEdit ? "Edit transaction" : "New transaction"}</DialogTitle>
        <DialogDescription>
          Amount is always positive — direction comes from the type.
        </DialogDescription>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Type</Label>
          <Select value={type} onValueChange={(v) => setType(v as typeof type)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="income">income</SelectItem>
              <SelectItem value="expense">expense</SelectItem>
              <SelectItem value="transfer">transfer</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Date</Label>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <Label>Amount</Label>
          <Input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            inputMode="decimal"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <Label>Category</Label>
          <Select value={category || "__none__"} onValueChange={(v) => setCategory(v === "__none__" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="(none)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(none)</SelectItem>
              {filteredCats.map((c) => (
                <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Account</Label>
          <Select value={account || "__none__"} onValueChange={(v) => setAccount(v === "__none__" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="(none)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(none)</SelectItem>
              {accounts.map((a) => (
                <SelectItem key={a.id} value={a.nickname}>{a.nickname}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex items-center gap-2 pt-2">
        <Switch checked={isTest} onCheckedChange={setIsTest} id="isTest" />
        <Label htmlFor="isTest" className="cursor-pointer">
          Mark as test (excluded from summaries by default)
        </Label>
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : isEdit ? "Save changes" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}
