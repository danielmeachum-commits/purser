import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Folder, Pencil, Plus } from "lucide-react";
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
import { api } from "@/lib/api";
import { useTableSort } from "@/lib/useTableSort";
import { formatCurrency } from "@/lib/utils";

interface Category {
  id: number;
  name: string;
  type: "income" | "expense" | "transfer";
  parent: string | null;
  is_active: boolean;
  monthly_budget: string | null;
  target_amount: string | null;
}

export default function Categories() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);
  const catsQ = useQuery({
    queryKey: ["cats-all"],
    queryFn: () => api<Category[]>("/categories", { query: { include_inactive: true } }),
  });

  const grouped = useMemo(() => {
    const data = catsQ.data ?? [];
    // Group by type, then parent first then children for a nicer default ordering.
    const order = { expense: 0, income: 1, transfer: 2 } as const;
    return [...data].sort((a, b) => {
      if (a.type !== b.type) return order[a.type] - order[b.type];
      const ap = a.parent ?? "";
      const bp = b.parent ?? "";
      if (ap !== bp) return ap.localeCompare(bp);
      return a.name.localeCompare(b.name);
    });
  }, [catsQ.data]);

  const { sorted: rows, sort, toggle } = useTableSort<
    Category,
    "name" | "type" | "parent" | "budget" | "status"
  >(grouped, {
    storageKey: "budget.sort.categories",
    columns: {
      name: { accessor: (c) => c.name },
      type: { accessor: (c) => c.type },
      parent: { accessor: (c) => c.parent },
      budget: { accessor: (c) => (c.monthly_budget ? Number(c.monthly_budget) : null) },
      status: { accessor: (c) => (c.is_active ? "active" : "inactive") },
    },
  });

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Categories"
        description="Spending and income buckets. Sub-categories inherit their parent's type."
        actions={
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
        }
      />

      <Card className="overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState
            icon={<Folder className="h-5 w-5" />}
            title="No categories yet"
            description="Add categories like “food” or “salary” to organize transactions."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader sortKey="name" sort={sort} onToggle={toggle}>
                  Name
                </SortableHeader>
                <SortableHeader className="w-28" sortKey="type" sort={sort} onToggle={toggle}>
                  Type
                </SortableHeader>
                <SortableHeader sortKey="parent" sort={sort} onToggle={toggle}>
                  Parent
                </SortableHeader>
                <SortableHeader className="w-32 text-right" sortKey="budget" sort={sort} onToggle={toggle}>
                  Monthly budget
                </SortableHeader>
                <SortableHeader className="w-24" sortKey="status" sort={sort} onToggle={toggle}>
                  Status
                </SortableHeader>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">
                    {c.parent && <span className="text-muted-foreground">↳ </span>}
                    {c.name}
                  </TableCell>
                  <TableCell><Badge variant={c.type}>{c.type}</Badge></TableCell>
                  <TableCell className="text-muted-foreground">{c.parent ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {c.monthly_budget ? formatCurrency(c.monthly_budget) : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={c.is_active ? "income" : "outline"}>
                      {c.is_active ? "active" : "inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end">
                      <Button size="icon" variant="ghost" onClick={() => setEditing(c)} aria-label="Edit">
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
  const [monthlyBudget, setMonthlyBudget] = useState(category?.monthly_budget ?? "");
  const [targetAmount, setTargetAmount] = useState(category?.target_amount ?? "");
  const [error, setError] = useState<string | null>(null);

  const parentOptions = useMemo(
    () => all.filter((c) => c.type === type && !c.parent && c.id !== category?.id),
    [all, type, category?.id],
  );

  const save = useMutation({
    mutationFn: async () => {
      const trimmedBudget = monthlyBudget.trim();
      const trimmedTarget = targetAmount.trim();
      if (isEdit) {
        const body: Record<string, unknown> = {
          name,
          parent: parent || "",
          is_active: isActive,
        };
        if (trimmedBudget === "") body.clear_monthly_budget = true;
        else body.monthly_budget = trimmedBudget;
        if (trimmedTarget === "") body.clear_target_amount = true;
        else body.target_amount = trimmedTarget;
        return api(`/categories/${category!.id}`, { method: "PATCH", body });
      }
      const body: Record<string, unknown> = { name, type, parent: parent || null };
      if (trimmedBudget !== "") body.monthly_budget = trimmedBudget;
      if (trimmedTarget !== "") body.target_amount = trimmedTarget;
      return api("/categories", { method: "POST", body });
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
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. groceries"
            required
          />
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
        <div className="space-y-2">
          <Label>Monthly budget (optional)</Label>
          <Input
            value={monthlyBudget}
            onChange={(e) => setMonthlyBudget(e.target.value)}
            placeholder="e.g. 500"
            inputMode="decimal"
          />
        </div>
        <div className="space-y-2">
          <Label>Target amount (optional)</Label>
          <Input
            value={targetAmount}
            onChange={(e) => setTargetAmount(e.target.value)}
            placeholder="e.g. 5000"
            inputMode="decimal"
          />
        </div>
        {isEdit && (
          <div className="col-span-2 flex items-center gap-2 pt-1">
            <Switch checked={isActive} onCheckedChange={setIsActive} id="cat-active" />
            <Label htmlFor="cat-active" className="cursor-pointer">
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
