import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Accounts</h1>
          <p className="text-sm text-muted-foreground">Your real-world accounts.</p>
        </div>
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4 mr-2" /> New account</Button>
          </DialogTrigger>
          <DialogContent>
            <AccountForm types={typesQ.data ?? []} onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["accts-all"] }); }} />
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nickname</TableHead>
            <TableHead>Bank</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Last 4</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(acctsQ.data ?? []).map((a) => (
            <TableRow key={a.id}>
              <TableCell className="font-medium">{a.nickname}</TableCell>
              <TableCell>{a.bank_name}</TableCell>
              <TableCell>{a.account_type}</TableCell>
              <TableCell>{a.last_four ?? "—"}</TableCell>
              <TableCell>
                <Badge variant={a.is_active ? "income" : "outline"}>
                  {a.is_active ? "active" : "inactive"}
                </Badge>
              </TableCell>
              <TableCell>
                <Button size="icon" variant="ghost" onClick={() => setEditing(a)}>
                  <Pencil className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

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
          <Input value={nickname} onChange={(e) => setNickname(e.target.value)} required />
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
          <Input value={lastFour} onChange={(e) => setLastFour(e.target.value)} maxLength={4} />
        </div>
        {isEdit && (
          <div className="flex items-center gap-2">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="acct-active" />
            <Label htmlFor="acct-active">Active</Label>
          </div>
        )}
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
      </DialogFooter>
    </form>
  );
}
