import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Plus, Trash2 } from "lucide-react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

interface Token {
  id: number;
  name: string;
  scope: "admin" | "read";
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

interface TokenCreated extends Token {
  token: string;
}

export default function Tokens() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<TokenCreated | null>(null);

  const tokensQ = useQuery({ queryKey: ["tokens"], queryFn: () => api<Token[]>("/auth/tokens") });

  const revoke = useMutation({
    mutationFn: (id: number) => api<void>(`/auth/tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Service tokens</h1>
          <p className="text-sm text-muted-foreground">
            For read-only dashboard URLs and external integrations.
          </p>
        </div>
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4 mr-2" /> New token</Button>
          </DialogTrigger>
          <DialogContent>
            <NewTokenForm
              onDone={(created) => {
                setCreating(false);
                setJustCreated(created);
                qc.invalidateQueries({ queryKey: ["tokens"] });
              }}
            />
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Scope</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Last used</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(tokensQ.data ?? []).map((t) => (
            <TableRow key={t.id}>
              <TableCell className="font-medium">{t.name}</TableCell>
              <TableCell><Badge variant={t.scope === "admin" ? "default" : "secondary"}>{t.scope}</Badge></TableCell>
              <TableCell>{formatDate(t.created_at)}</TableCell>
              <TableCell>{t.last_used_at ? formatDate(t.last_used_at) : "—"}</TableCell>
              <TableCell>
                {t.revoked_at ? (
                  <Badge variant="outline">revoked</Badge>
                ) : (
                  <Badge variant="income">active</Badge>
                )}
              </TableCell>
              <TableCell>
                {!t.revoked_at && (
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => { if (confirm(`Revoke ${t.name}?`)) revoke.mutate(t.id); }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={!!justCreated} onOpenChange={(open) => !open && setJustCreated(null)}>
        <DialogContent>
          {justCreated && (
            <>
              <DialogHeader>
                <DialogTitle>Token created</DialogTitle>
                <DialogDescription>
                  Copy this now — you won't see it again.
                </DialogDescription>
              </DialogHeader>
              <div className="rounded-md border bg-muted/30 p-3 font-mono text-xs break-all">
                {justCreated.token}
              </div>
              {justCreated.scope === "read" && (
                <div className="rounded-md border bg-muted/30 p-3 text-sm">
                  Dashboard URL:{" "}
                  <code className="break-all">
                    {window.location.origin}/dashboard?token={justCreated.token}
                  </code>
                </div>
              )}
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => navigator.clipboard.writeText(justCreated.token)}
                >
                  <Copy className="h-4 w-4 mr-2" /> Copy token
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NewTokenForm({ onDone }: { onDone: (created: TokenCreated) => void }) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"admin" | "read">("read");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api<TokenCreated>("/auth/tokens", { method: "POST", body: { name, scope } }),
    onSuccess: onDone,
    onError: (e: unknown) => setError(e instanceof Error ? e.message : "failed"),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    create.mutate();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>New service token</DialogTitle>
      </DialogHeader>
      <div className="space-y-2">
        <Label>Name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="wall-display" required />
      </div>
      <div className="space-y-2">
        <Label>Scope</Label>
        <Select value={scope} onValueChange={(v) => setScope(v as "admin" | "read")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="read">read (dashboard)</SelectItem>
            <SelectItem value="admin">admin (full)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create"}</Button>
      </DialogFooter>
    </form>
  );
}
