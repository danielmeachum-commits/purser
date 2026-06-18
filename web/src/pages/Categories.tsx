import { type FormEvent, useMemo, useState } from "react";
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

interface Category {
  id: number;
  name: string;
  type: "income" | "expense" | "transfer";
  parent: string | null;
  is_active: boolean;
}

export default function Categories() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);
  const catsQ = useQuery({
    queryKey: ["cats-all"],
    queryFn: () => api<Category[]>("/categories", { query: { include_inactive: true } }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Categories</h1>
          <p className="text-sm text-muted-foreground">Spending and income categories.</p>
        </div>
        <Dialog open={creating} onOpenChange={setCreating}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4 mr-2" /> New category</Button>
          </DialogTrigger>
          <DialogContent>
            <CategoryForm
              all={catsQ.data ?? []}
              onDone={() => { setCreating(false); qc.invalidateQueries({ queryKey: ["cats-all"] }); }}
            />
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Parent</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-16" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(catsQ.data ?? []).map((c) => (
            <TableRow key={c.id}>
              <TableCell className="font-medium">{c.name}</TableCell>
              <TableCell><Badge variant={c.type}>{c.type}</Badge></TableCell>
              <TableCell>{c.parent ?? "—"}</TableCell>
              <TableCell>
                <Badge variant={c.is_active ? "income" : "outline"}>
                  {c.is_active ? "active" : "inactive"}
                </Badge>
              </TableCell>
              <TableCell>
                <Button size="icon" variant="ghost" onClick={() => setEditing(c)}>
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
            <CategoryForm
              category={editing}
              all={catsQ.data ?? []}
              onDone={() => { setEditing(null); qc.invalidateQueries({ queryKey: ["cats-all"] }); }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CategoryForm({
  category,
  all,
  onDone,
}: {
  category?: Category;
  all: Category[];
  onDone: () => void;
}) {
  const isEdit = !!category;
  const [name, setName] = useState(category?.name ?? "");
  const [type, setType] = useState<Category["type"]>(category?.type ?? "expense");
  const [parent, setParent] = useState(category?.parent ?? "");
  const [isActive, setIsActive] = useState(category?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const parentOptions = useMemo(
    () => all.filter((c) => c.type === type && !c.parent && c.id !== category?.id),
    [all, type, category?.id],
  );

  const save = useMutation({
    mutationFn: async () => {
      if (isEdit) {
        return api(`/categories/${category!.id}`, {
          method: "PATCH",
          body: { name, parent: parent || "", is_active: isActive },
        });
      }
      return api("/categories", {
        method: "POST",
        body: { name, type, parent: parent || null },
      });
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
        <DialogTitle>{isEdit ? "Edit category" : "New category"}</DialogTitle>
      </DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2 col-span-2">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <Label>Type</Label>
          <Select value={type} onValueChange={(v) => setType(v as Category["type"])} disabled={isEdit}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="expense">expense</SelectItem>
              <SelectItem value="income">income</SelectItem>
              <SelectItem value="transfer">transfer</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Parent (optional)</Label>
          <Select value={parent || "__none__"} onValueChange={(v) => setParent(v === "__none__" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="(top-level)" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(top-level)</SelectItem>
              {parentOptions.map((p) => <SelectItem key={p.id} value={p.name}>{p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {isEdit && (
          <div className="flex items-center gap-2">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="cat-active" />
            <Label htmlFor="cat-active">Active</Label>
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
