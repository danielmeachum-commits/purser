import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
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

  const txQ = useQuery({ queryKey: ["txs"], queryFn: () => api<Tx[]>("/transactions", { query: { limit: 200, test_mode: "include" } }) });
  const catsQ = useQuery({ queryKey: ["cats"], queryFn: () => api<Cat[]>("/categories") });
  const acctsQ = useQuery({ queryKey: ["accts"], queryFn: () => api<Acct[]>("/accounts") });

  const del = useMutation({
    mutationFn: (id: number) => api<void>(`/transactions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["txs"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Transactions</h1>
          <p className="text-sm text-muted-foreground">All recorded transactions.</p>
        </div>
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
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Account</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(txQ.data ?? []).map((tx) => (
            <TableRow key={tx.id}>
              <TableCell className="whitespace-nowrap">{formatDate(tx.date)}</TableCell>
              <TableCell>
                {tx.description}
                {tx.is_test && (
                  <Badge variant="outline" className="ml-2">
                    test
                  </Badge>
                )}
              </TableCell>
              <TableCell><Badge variant={tx.type}>{tx.type}</Badge></TableCell>
              <TableCell>{tx.category ?? "—"}</TableCell>
              <TableCell>{tx.account ?? "—"}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCurrency(tx.amount)}</TableCell>
              <TableCell>
                <div className="flex gap-1 justify-end">
                  <Button size="icon" variant="ghost" onClick={() => setEditing(tx)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => {
                      if (confirm(`Delete transaction "${tx.description}"?`)) del.mutate(tx.id);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

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
        <DialogDescription>All fields except category and account are required.</DialogDescription>
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
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" required />
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
      <div className="flex items-center gap-2">
        <Switch checked={isTest} onCheckedChange={setIsTest} id="isTest" />
        <Label htmlFor="isTest">Test transaction</Label>
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
