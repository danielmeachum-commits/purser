import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

interface AccountType { id: number; name: string }
interface TransactionType { id: number; name: string; sign: number }

export default function Types() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);

  const acctTypesQ = useQuery({ queryKey: ["acct-types"], queryFn: () => api<AccountType[]>("/account-types") });
  const txTypesQ = useQuery({ queryKey: ["tx-types"], queryFn: () => api<TransactionType[]>("/transaction-types") });

  const del = useMutation({
    mutationFn: (id: number) => api<void>(`/account-types/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acct-types"] }),
    onError: (e: unknown) => alert(e instanceof Error ? e.message : "failed"),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <section className="space-y-4">
        <PageHeader
          title="Account types"
          description="Buckets like checking, savings, credit card. Used to categorize accounts."
          actions={
            <Dialog open={creating} onOpenChange={setCreating}>
              <DialogTrigger asChild>
                <Button><Plus className="h-4 w-4 mr-2" /> New type</Button>
              </DialogTrigger>
              <DialogContent>
                <NewTypeForm onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["acct-types"] }); }} />
              </DialogContent>
            </Dialog>
          }
        />
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(acctTypesQ.data ?? []).map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => { if (confirm(`Delete ${t.name}?`)) del.mutate(t.id); }}
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
        </Card>
      </section>

      <section className="space-y-4">
        <PageHeader
          title="Transaction types"
          description="Read-only — these drive the signing math (+1 income, –1 expense, 0 transfer)."
        />
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Sign</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(txTypesQ.data ?? []).map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <Badge variant={t.name as "income" | "expense" | "transfer"}>{t.name}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {t.sign > 0 ? `+${t.sign}` : t.sign}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </section>
    </div>
  );
}

function NewTypeForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api("/account-types", { method: "POST", body: { name } }),
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
        <DialogTitle>New account type</DialogTitle>
      </DialogHeader>
      <div className="space-y-2">
        <Label>Name</Label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. brokerage"
          required
        />
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}
