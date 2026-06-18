import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react";
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
  const [copied, setCopied] = useState<"token" | "url" | null>(null);

  const tokensQ = useQuery({ queryKey: ["tokens"], queryFn: () => api<Token[]>("/auth/tokens") });

  const revoke = useMutation({
    mutationFn: (id: number) => api<void>(`/auth/tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }),
  });

  const copy = async (text: string, kind: "token" | "url") => {
    await navigator.clipboard.writeText(text);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1800);
  };

  const rows = tokensQ.data ?? [];
  const dashboardUrl = justCreated
    ? `${window.location.origin}/dashboard?token=${justCreated.token}`
    : "";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Service tokens"
        description="Bearer tokens for read-only dashboard URLs and external integrations."
        actions={
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
        }
      />

      <Card className="overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState
            icon={<KeyRound className="h-5 w-5" />}
            title="No tokens yet"
            description="Create one to share a read-only dashboard URL or grant API access."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="w-24">Scope</TableHead>
                <TableHead className="w-28">Created</TableHead>
                <TableHead className="w-28">Last used</TableHead>
                <TableHead className="w-24">Status</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell>
                    <Badge variant={t.scope === "admin" ? "default" : "secondary"}>{t.scope}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(t.created_at)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {t.last_used_at ? formatDate(t.last_used_at) : "—"}
                  </TableCell>
                  <TableCell>
                    {t.revoked_at ? (
                      <Badge variant="outline">revoked</Badge>
                    ) : (
                      <Badge variant="income">active</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      {!t.revoked_at && (
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => { if (confirm(`Revoke ${t.name}?`)) revoke.mutate(t.id); }}
                          aria-label="Revoke"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={!!justCreated} onOpenChange={(open) => !open && setJustCreated(null)}>
        <DialogContent>
          {justCreated && (
            <>
              <DialogHeader>
                <DialogTitle>Token created</DialogTitle>
                <DialogDescription>
                  Copy this now — the secret won't be shown again.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                    Bearer token
                  </Label>
                  <div className="flex gap-2">
                    <div className="flex-1 rounded-md border bg-muted/30 p-2.5 font-mono text-xs break-all">
                      {justCreated.token}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={() => copy(justCreated.token, "token")}
                      aria-label="Copy token"
                    >
                      {copied === "token" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
                {justCreated.scope === "read" && (
                  <div className="space-y-1.5">
                    <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                      Dashboard URL
                    </Label>
                    <div className="flex gap-2">
                      <div className="flex-1 rounded-md border bg-muted/30 p-2.5 font-mono text-xs break-all">
                        {dashboardUrl}
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => copy(dashboardUrl, "url")}
                        aria-label="Copy URL"
                      >
                        {copied === "url" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setJustCreated(null)}>
                  Done
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
        <DialogDescription>
          Read tokens are for dashboard URLs. Admin tokens can write — keep them safe.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3">
        <div className="space-y-2">
          <Label>Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="wall-display"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Scope</Label>
          <Select value={scope} onValueChange={(v) => setScope(v as "admin" | "read")}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="read">read (dashboard)</SelectItem>
              <SelectItem value="admin">admin (full API)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      {error && <div className="text-sm text-destructive">{error}</div>}
      <DialogFooter>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}
