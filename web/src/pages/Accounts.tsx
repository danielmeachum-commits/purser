import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Pencil, Plus } from "lucide-react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

interface Account {
  id: number;
  nickname: string;
  bank_name: string;
  account_type: string;
  last_four: string | null;
  is_active: boolean;
}

interface AccountType { id: number; name: string }

export default function Accounts() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);

  const acctsQ = useQuery({
    queryKey: ["accts-all"],
    queryFn: () => api<Account[]>("/accounts", { query: { include_inactive: true } }),
  });
  const typesQ = useQuery({ queryKey: ["acct-types"], queryFn: () => api<AccountType[]>("/account-types") });

  const rows = acctsQ.data ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Accounts"
        description="Real-world checking, savings, and credit cards. Deactivate (don't delete) old ones."
        actions={
          <Dialog open={creating} onOpenChange={setCreating}>
            <DialogTrigger asChild>
              <Button><Plus className="h-4 w-4 mr-2" /> New account</Button>
            </DialogTrigger>
            <DialogContent>
              <AccountForm
                types={typesQ.data ?? []}
                onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["accts-all"] }); }}
              />
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState
            icon={<CreditCard className="h-5 w-5" />}
            title="No accounts yet"
            description="Add your first account so transactions can be tagged to it."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nickname</TableHead>
                <TableHead>Bank</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="w-20">Last 4</TableHead>
                <TableHead className="w-24">Status</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.nickname}</TableCell>
                  <TableCell>{a.bank_name}</TableCell>
                  <TableCell className="text-muted-foreground">{a.account_type}</TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {a.last_four ? `••${a.last_four}` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={a.is_active ? "income" : "outline"}>
                      {a.is_active ? "active" : "inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <Button size="icon" variant="ghost" onClick={() => setEditing(a)} aria-label="Edit">
                        <Pencil className="h-4 w-4" />
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
            <AccountForm
              account={editing}
              types={typesQ.data ?? []}
              onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["accts-all"] }); }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AccountForm({
  account,
  types,
  onDone,
}: {
  account?: Account;
  types: AccountType[];
  onDone: () => void;
}) {
  const isEdit = !!account;
  const [nickname, setNickname] = useState(account?.nickname ?? "");
  const [bankName, setBankName] = useState(account?.bank_name ?? "");
  const [accountType, setAccountType] = useState(account?.account_type ?? types[0]?.name ?? "");
  const [lastFour, setLastFour] = useState(account?.last_four ?? "");
  const [isActive, setIsActive] = useState(account?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        nickname,
        bank_name: bankName,
        account_type: accountType,
        last_four: lastFour || null,
      };
      if (isEdit) body.is_active = isActive;
      if (isEdit) return api(`/accounts/${account!.id}`, { method: "PATCH", body });
      return api("/accounts", { method: "POST", body });
    },
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
        <DialogTitle>{isEdit ? "Edit account" : "New account"}</DialogTitle>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2 col-span-2">
          <Label>Nickname</Label>
          <Input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="e.g. chase checking"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Bank</Label>
          <Input value={bankName} onChange={(e) => setBankName(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <Label>Type</Label>
          <Select value={accountType} onValueChange={setAccountType}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {types.map((t) => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Last 4</Label>
          <Input
            value={lastFour}
            onChange={(e) => setLastFour(e.target.value)}
            maxLength={4}
            inputMode="numeric"
            placeholder="1234"
          />
        </div>
        {isEdit && (
          <div className="col-span-2 flex items-center gap-2 pt-1">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="acct-active" />
            <Label htmlFor="acct-active" className="cursor-pointer">
              Active
            </Label>
          </div>
        )}
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
